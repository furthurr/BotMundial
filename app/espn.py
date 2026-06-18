import datetime
import logging
import re
import time
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from app import config

logger = logging.getLogger(__name__)


# --- Cache -----------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Optional[Any]:
    if config.ESPN_CACHE_TTL_SECONDS <= 0:
        return None
    entry = _cache.get(key)
    if not entry:
        return None
    ts, payload = entry
    if (time.monotonic() - ts) > config.ESPN_CACHE_TTL_SECONDS:
        return None
    logger.debug("ESPN cache hit for %s", key)
    return payload


def _cache_set(key: str, payload: Any) -> None:
    if config.ESPN_CACHE_TTL_SECONDS <= 0:
        return
    _cache[key] = (time.monotonic(), payload)


# --- Public API ------------------------------------------------------------


async def fetch_world_cup_scoreboard(
    date_from: datetime.date,
    date_to: datetime.date,
) -> list[dict[str, Any]]:
    """Fetch the scoreboard for the given date range and return only World Cup 2026 events.

    Returns a list of normalized event dicts. The dict has the shape:
        {
            "id": str,
            "date_utc": datetime.datetime,
            "state": "pre" | "in" | "post",
            "display_clock": str | None,
            "completed": bool,
            "home": {"name": str, "score": int | None},
            "away": {"name": str, "score": int | None},
            "league_name": str | None,
        }
    """
    date_from_str = date_from.strftime("%Y%m%d")
    date_to_str = date_to.strftime("%Y%m%d")
    cache_key = f"scoreboard:{date_from_str}-{date_to_str}"

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{config.ESPN_BASE_URL}/{config.ESPN_LEAGUE_SLUG}/scoreboard"
    params = {"dates": f"{date_from_str}-{date_to_str}"}
    headers = {
        "User-Agent": f"{config.BOT_NAME}/{config.BOT_VERSION}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=config.ESPN_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params, headers=headers)
    except httpx.TimeoutException:
        logger.error("ESPN request timed out (%ss) for %s", config.ESPN_REQUEST_TIMEOUT_SECONDS, url)
        raise
    except httpx.HTTPError as exc:
        logger.error("ESPN HTTP error: %s", exc)
        raise

    if response.status_code != 200:
        logger.error("ESPN non-200 status: %s body=%s", response.status_code, response.text[:200])
        raise RuntimeError(f"ESPN returned status {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        logger.error("ESPN invalid JSON: %s", exc)
        raise RuntimeError("ESPN returned invalid JSON") from exc

    events = payload.get("events") or []
    logger.info("ESPN returned %d raw events for %s", len(events), cache_key)

    world_cup_pattern = re.compile(config.ESPN_WORLD_CUP_FILTER_REGEX, re.IGNORECASE)
    normalized: list[dict[str, Any]] = []
    for event in events:
        if not _is_world_cup_2026(event, world_cup_pattern):
            continue
        try:
            normalized.append(_normalize_event(event))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed ESPN event %s: %s", event.get("id"), exc)
            continue

    logger.info("Filtered to %d World Cup 2026 events", len(normalized))
    _cache_set(cache_key, normalized)
    return normalized


# --- Helpers ---------------------------------------------------------------


def _is_world_cup_2026(event: dict[str, Any], pattern: re.Pattern[str]) -> bool:
    leagues = event.get("leagues") or []
    season_year: Optional[int] = None
    season = event.get("season") or {}
    if isinstance(season, dict):
        try:
            season_year = int(season.get("year")) if season.get("year") is not None else None
        except (TypeError, ValueError):
            season_year = None

    for league in leagues:
        if not isinstance(league, dict):
            continue
        name = league.get("name") or league.get("shortName") or league.get("abbreviation") or ""
        if pattern.search(str(name)):
            # If a season year is known, accept only 2026; otherwise accept (some
            # endpoints omit the field for the active season).
            if season_year is None or season_year == 2026:
                return True

    # Fallback: competition's notes/altGameNote may carry a "FIFA World Cup" tag
    competitions = event.get("competitions") or []
    for comp in competitions:
        if not isinstance(comp, dict):
            continue
        alt = comp.get("altGameNote") or comp.get("notes") or []
        if isinstance(alt, list):
            joined = " ".join(str(n) for n in alt)
        else:
            joined = str(alt)
        if pattern.search(joined):
            if season_year is None or season_year == 2026:
                return True

    return False


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    competitions = event.get("competitions") or []
    if not competitions:
        raise ValueError("event without competitions")
    competition = competitions[0]

    status = competition.get("status") or {}
    status_type = status.get("type") or {}
    state = status_type.get("state") or "pre"
    completed = bool(status_type.get("completed"))
    display_clock = status.get("displayClock")

    competitors = competition.get("competitors") or []
    home = None
    away = None
    for comp in competitors:
        if comp.get("homeAway") == "home":
            home = comp
        elif comp.get("homeAway") == "away":
            away = comp

    if home is None or away is None:
        raise ValueError("event missing home/away competitor")

    def _score(value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _team_info(competitor: dict[str, Any]) -> dict[str, Any]:
        team = competitor.get("team") or {}
        name = (
            team.get("shortDisplayName")
            or team.get("displayName")
            or team.get("name")
            or team.get("abbreviation")
            or "?"
        )
        return {
            "name": name,
            "display_name": team.get("displayName") or name,
            "abbreviation": team.get("abbreviation") or "",
        }

    date_raw = event.get("date")
    if not date_raw:
        raise ValueError("event without date")
    # ESPN emits "2026-05-24T19:00Z" (sometimes with milliseconds)
    cleaned = date_raw.replace("Z", "+00:00")
    date_utc = datetime.datetime.fromisoformat(cleaned)

    leagues = event.get("leagues") or []
    league_name = None
    if leagues:
        league_name = leagues[0].get("shortName") or leagues[0].get("name")

    home_info = _team_info(home)
    away_info = _team_info(away)

    return {
        "id": str(event.get("id") or ""),
        "date_utc": date_utc,
        "state": state,
        "display_clock": display_clock,
        "completed": completed,
        "home": {**home_info, "score": _score(home.get("score"))},
        "away": {**away_info, "score": _score(away.get("score"))},
        "league_name": league_name,
    }


def local_day_for_event(event: dict[str, Any], tz: ZoneInfo) -> datetime.date:
    return event["date_utc"].astimezone(tz).date()


# --- Standings (group tables) ----------------------------------------------


async def fetch_world_cup_standings() -> list[dict[str, Any]]:
    """Fetch the World Cup 2026 group standings.

    Returns a list of groups, each normalized as:
        {
            "group_name": "Grupo A",
            "teams": [
                {
                    "rank": int,
                    "display_name": str,
                    "abbreviation": str,
                    "played": int,
                    "points": int,
                    "gd": str,   # signed string, e.g. "+2", "-1", "0"
                },
                ...  # sorted by rank ascending
            ],
        },
        ...
    """
    cache_key = "standings"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{config.ESPN_STANDINGS_BASE_URL}/{config.ESPN_LEAGUE_SLUG}/standings"
    headers = {
        "User-Agent": f"{config.BOT_NAME}/{config.BOT_VERSION}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=config.ESPN_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        logger.error("ESPN standings timed out (%ss) for %s", config.ESPN_REQUEST_TIMEOUT_SECONDS, url)
        raise
    except httpx.HTTPError as exc:
        logger.error("ESPN standings HTTP error: %s", exc)
        raise

    if response.status_code != 200:
        logger.error("ESPN standings non-200: %s body=%s", response.status_code, response.text[:200])
        raise RuntimeError(f"ESPN standings returned status {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        logger.error("ESPN standings invalid JSON: %s", exc)
        raise RuntimeError("ESPN standings returned invalid JSON") from exc

    season = payload.get("season") or {}
    season_year = season.get("year")
    if season_year is not None and int(season_year) != 2026:
        logger.warning("ESPN standings season is %s, not 2026; returning empty", season_year)
        return []

    children = payload.get("children") or []
    groups: list[dict[str, Any]] = []
    for child in children:
        try:
            group = _normalize_group(child)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed group %s: %s", child.get("name"), exc)
            continue
        if group["teams"]:
            groups.append(group)

    logger.info("ESPN standings: %d groups parsed", len(groups))
    _cache_set(cache_key, groups)
    return groups


def _localize_group_name(name: str) -> str:
    if name.lower().startswith("group "):
        return "Grupo " + name[len("group "):]
    return name


def _normalize_group(child: dict[str, Any]) -> dict[str, Any]:
    group_name = _localize_group_name(child.get("name") or "Grupo ?")
    standings = child.get("standings") or {}
    entries = standings.get("entries") or []

    teams: list[dict[str, Any]] = []
    for entry in entries:
        team = entry.get("team") or {}
        note = entry.get("note") or {}
        stats_by_name = {
            s.get("name"): s
            for s in (entry.get("stats") or [])
            if isinstance(s, dict)
        }

        def _stat_str(name: str, default: str = "0") -> str:
            s = stats_by_name.get(name)
            if not s:
                return default
            return str(s.get("displayValue") if s.get("displayValue") is not None else default)

        def _stat_int(name: str, default: int = 0) -> int:
            s = stats_by_name.get(name)
            if not s:
                return default
            value = s.get("value")
            if value is None:
                try:
                    return int(str(s.get("displayValue")).lstrip("+"))
                except (TypeError, ValueError):
                    return default
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        rank = note.get("rank")
        if rank is None:
            rank = _stat_int("rank", 0)
        try:
            rank = int(rank)
        except (TypeError, ValueError):
            rank = 0

        teams.append(
            {
                "rank": rank,
                "display_name": team.get("displayName") or team.get("name") or "?",
                "abbreviation": team.get("abbreviation") or "",
                "played": _stat_int("gamesPlayed", 0),
                "points": _stat_int("points", 0),
                "gd": _stat_str("pointDifferential", "0"),
            }
        )

    # ESPN entries are NOT pre-sorted; sort by rank, then points desc, then GD desc.
    def _sort_key(t: dict[str, Any]) -> tuple[int, int, int]:
        rank = t["rank"] if t["rank"] else 99
        gd_num = 0
        try:
            gd_num = int(str(t["gd"]).replace("+", ""))
        except (TypeError, ValueError):
            gd_num = 0
        return (rank, -t["points"], -gd_num)

    teams.sort(key=_sort_key)
    return {"group_name": group_name, "teams": teams}
