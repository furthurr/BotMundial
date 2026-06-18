import datetime
import html
import logging
from typing import Iterable, Literal
from zoneinfo import ZoneInfo

from app.forecast import forecast
from app.teams import team_parts

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096

_DAY_KIND = Literal["yesterday", "today", "tomorrow"]

_SPANISH_WEEKDAYS = [
    "lunes", "martes", "miércoles", "jueves",
    "viernes", "sábado", "domingo",
]

_SPANISH_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# Column widths (in characters) for the monospaced table.
_W_ABBR = 3       # team abbreviation (ESP, BRA, ...)
_W_MID = 14       # score / time / live column


def fmt_mx_time(dt_local: datetime.datetime) -> str:
    """Format a local datetime as 'h:mm a. m.' / 'h:mm p. m.' (Mexico style).

    Locale-independent: computes the 12-hour clock and AM/PM manually so the
    output is identical regardless of the system locale.
    """
    hour_24 = dt_local.hour
    minute = dt_local.minute
    suffix = "a. m." if hour_24 < 12 else "p. m."
    hour_12 = hour_24 % 12
    if hour_12 == 0:
        hour_12 = 12
    return f"{hour_12}:{minute:02d} {suffix}"


def fmt_mx_date(d: datetime.date) -> str:
    weekday = _SPANISH_WEEKDAYS[d.weekday()]
    month = _SPANISH_MONTHS[d.month - 1]
    return f"{weekday} {d.day} de {month} de {d.year}"


# --- Row building ----------------------------------------------------------


def _format_final_score(event: dict) -> str:
    home = event["home"]["score"]
    away = event["away"]["score"]
    if home is None or away is None:
        return "— - —"
    return f"{home} - {away}"


def _live_state(event: dict) -> str:
    """State label for a live match, including the current minute.

    e.g. "EN VIVO 62'"  /  "EN VIVO 90'+6'"
    """
    clock = (event.get("display_clock") or "").strip()
    if not clock or clock.upper() in {"FT", "HT"}:
        return "EN VIVO"
    return f"EN VIVO {clock}"


def _format_kickoff_time(event: dict, tz: ZoneInfo) -> str:
    local_dt = event["date_utc"].astimezone(tz)
    return fmt_mx_time(local_dt)


def _middle_and_state(event: dict, day_kind: _DAY_KIND, tz: ZoneInfo) -> tuple[str, str]:
    state = event["state"]
    if day_kind == "yesterday":
        return _format_final_score(event), "Final"
    if day_kind == "tomorrow":
        return _format_kickoff_time(event, tz), "Prog."
    # today
    if state == "post" or event.get("completed"):
        return _format_final_score(event), "Final"
    if state == "in":
        return _format_final_score(event), _live_state(event)
    return _format_kickoff_time(event, tz), "Prog."


def _format_table_row(event: dict, day_kind: _DAY_KIND, tz: ZoneInfo) -> str:
    """Build one monospaced row:

        🇪🇸 ESP   2 - 0      🇧🇷 BRA   Final

    The flag sits at the edges; the textual columns are padded so that the
    middle (score/time) column stays aligned across rows.
    """
    home = event["home"]
    away = event["away"]
    home_flag, home_abbr = team_parts(home.get("display_name", home.get("name", "")), home.get("abbreviation", ""))
    away_flag, away_abbr = team_parts(away.get("display_name", away.get("name", "")), away.get("abbreviation", ""))

    middle, state = _middle_and_state(event, day_kind, tz)

    home_abbr = home_abbr[:_W_ABBR].rjust(_W_ABBR)
    away_abbr = away_abbr[:_W_ABBR].ljust(_W_ABBR)
    middle = middle.center(_W_MID)

    # Local side: flag then abbr (right aligned). Visitor: abbr then flag-free.
    left = f"{home_flag} {home_abbr}"
    right = f"{away_flag} {away_abbr}"
    row = f"{left} {middle} {right}  {state}"
    return html.escape(row)


# --- Message assembly ------------------------------------------------------


def build_partidos_messages(
    events: Iterable[dict],
    today_local: datetime.date,
    tz: ZoneInfo,
) -> list[tuple[str, str]]:
    """Returns a list of (text, parse_mode) tuples ready to be sent.

    Each section (Ayer / Hoy / Mañana) is rendered as an HTML <pre> block so
    that Telegram uses a monospaced font and the columns stay aligned.
    """
    yesterday = today_local - datetime.timedelta(days=1)
    tomorrow = today_local + datetime.timedelta(days=1)

    by_day: dict[datetime.date, list[dict]] = {yesterday: [], today_local: [], tomorrow: []}
    for event in events:
        event_local_day = event["date_utc"].astimezone(tz).date()
        if event_local_day in by_day:
            by_day[event_local_day].append(event)

    for day in by_day:
        by_day[day].sort(key=lambda e: e["date_utc"])

    sections: list[tuple[str, str, list[dict], _DAY_KIND]] = [
        ("🕘", f"Ayer · {fmt_mx_date(yesterday)}", by_day[yesterday], "yesterday"),
        ("🕒", f"Hoy · {fmt_mx_date(today_local)}", by_day[today_local], "today"),
        ("🕗", f"Mañana · {fmt_mx_date(tomorrow)}", by_day[tomorrow], "tomorrow"),
    ]

    header = f"<b>⚽ Mundial 2026</b>\n<i>{html.escape(fmt_mx_date(today_local))}</i>"

    messages: list[tuple[str, str]] = []
    parts: list[str] = [header]

    for emoji, title, day_events, kind in sections:
        block = _build_section_block(emoji, title, day_events, kind, tz)
        # Keep sections together while under the limit; otherwise flush.
        candidate = "\n\n".join(parts + [block])
        if len(candidate) > TELEGRAM_MESSAGE_LIMIT and len(parts) > 0:
            messages.append(("\n\n".join(parts), "HTML"))
            parts = [block]
        else:
            parts.append(block)

    if parts:
        messages.append(("\n\n".join(parts), "HTML"))

    return messages


def _build_section_block(
    emoji: str,
    title: str,
    day_events: list[dict],
    kind: _DAY_KIND,
    tz: ZoneInfo,
) -> str:
    title_line = f"{emoji} <b>{html.escape(title)}</b>"
    if not day_events:
        return f"{title_line}\n<i>Sin partidos</i>"

    rows = [_format_table_row(event, kind, tz) for event in day_events]
    table = "<pre>" + "\n".join(rows) + "</pre>"
    return f"{title_line}\n{table}"


# --- Group standings -------------------------------------------------------

# Column widths for the compact group table.
_W_GRUPO_ABBR = 3   # team abbreviation
_W_GRUPO_PJ = 2     # games played
_W_GRUPO_GD = 3     # goal difference (signed)
_W_GRUPO_PTS = 3    # points


def _format_group_row(team: dict) -> str:
    flag, abbr = team_parts(team.get("display_name", ""), team.get("abbreviation", ""))
    rank = team.get("rank") or 0
    abbr = abbr[:_W_GRUPO_ABBR].ljust(_W_GRUPO_ABBR)
    pj = str(team.get("played", 0)).rjust(_W_GRUPO_PJ)
    gd = str(team.get("gd", "0")).rjust(_W_GRUPO_GD)
    pts = str(team.get("points", 0)).rjust(_W_GRUPO_PTS)
    row = f"{rank}  {flag} {abbr}  {pj}  {gd}  {pts}"
    return html.escape(row)


def _build_group_block(group: dict) -> str:
    title_line = f"📊 <b>{html.escape(group.get('group_name', 'Grupo ?'))}</b>"
    header_row = html.escape(" #  EQUIPO    PJ   DG  PTS")
    teams = group.get("teams") or []
    if not teams:
        return f"{title_line}\n<i>Sin datos</i>"
    rows = [header_row] + [_format_group_row(t) for t in teams]
    table = "<pre>" + "\n".join(rows) + "</pre>"
    return f"{title_line}\n{table}"


def build_grupos_messages(groups: Iterable[dict]) -> list[tuple[str, str]]:
    """Returns a list of (text, parse_mode) tuples for the group standings.

    Each group is an HTML <pre> block (monospaced). Groups are packed into as
    few messages as possible without ever splitting a group across messages.
    """
    header = "<b>🏆 Mundial 2026 — Tabla de grupos</b>"

    blocks = [_build_group_block(group) for group in groups]
    if not blocks:
        return [(f"{header}\n\n<i>No hay datos de grupos disponibles.</i>", "HTML")]

    messages: list[tuple[str, str]] = []
    parts: list[str] = [header]

    for block in blocks:
        candidate = "\n\n".join(parts + [block])
        if len(candidate) > TELEGRAM_MESSAGE_LIMIT and len(parts) > 0:
            messages.append(("\n\n".join(parts), "HTML"))
            parts = [block]
        else:
            parts.append(block)

    if parts:
        messages.append(("\n\n".join(parts), "HTML"))

    return messages


# --- Forecasts -------------------------------------------------------------

# Column widths for the forecast table. The flag emoji is kept outside the
# padded text so its (inconsistent) monospaced width doesn't break alignment;
# both lines share the same widths so columns line up vertically.
_W_PR_ABBR = 3      # team abbreviation (ESP, CAB, ...)
_W_PR_PCT = 4       # percentage cell, e.g. "91%" / " 6%" (right aligned in 3 + '%')
_W_PR_CENTER = 13   # center column: kickoff time / "EMP  6%"


def _format_forecast_row(event: dict, tz: ZoneInfo) -> str:
    """Two-line forecast entry for one upcoming match:

        🇪🇸 ESP        10:00 a. m.      🇨🇻 CAB
        🇪🇸 ESP 91%      EMP  6%        🇨🇻 CAB  3%
    """
    home = event["home"]
    away = event["away"]
    home_flag, home_abbr = team_parts(home.get("display_name", home.get("name", "")), home.get("abbreviation", ""))
    away_flag, away_abbr = team_parts(away.get("display_name", away.get("name", "")), away.get("abbreviation", ""))

    home_abbr_p = home_abbr[:_W_PR_ABBR].ljust(_W_PR_ABBR)
    away_abbr_p = away_abbr[:_W_PR_ABBR].ljust(_W_PR_ABBR)

    pl, pe, pv = forecast(
        home.get("display_name") or home.get("name") or "",
        away.get("display_name") or away.get("name") or "",
    )

    def _pct(v: int) -> str:
        return f"{v}%".rjust(_W_PR_PCT)

    kickoff = fmt_mx_time(event["date_utc"].astimezone(tz))

    # Build both lines with an IDENTICAL left/right prefix structure so columns
    # line up vertically. The flag's monospaced width is irregular, so instead
    # of padding by character count we reuse the exact same pieces on both lines:
    # the local block is always "<flag> <abbr> <cell>" where the cell is either
    # blanks (line 1) or the percentage (line 2), both _W_PR_PCT wide.
    blank_pct = " " * _W_PR_PCT

    left1 = f"{home_flag} {home_abbr_p} {blank_pct}"
    center1 = kickoff.center(_W_PR_CENTER)
    right1 = f"{away_flag} {away_abbr_p}"
    line1 = f"{left1}{center1}{right1}"

    left2 = f"{home_flag} {home_abbr_p} {_pct(pl)}"
    center2 = f"EMP {_pct(pe)}".center(_W_PR_CENTER)
    right2 = f"{away_flag} {away_abbr_p} {_pct(pv)}"
    line2 = f"{left2}{center2}{right2}"

    return html.escape(line1 + "\n" + line2)


def _build_forecast_section(emoji: str, title: str, day_events: list[dict], tz: ZoneInfo) -> str:
    title_line = f"{emoji} <b>{html.escape(title)}</b>"
    if not day_events:
        return f"{title_line}\n<i>Sin partidos por jugar</i>"
    rows = [_format_forecast_row(event, tz) for event in day_events]
    table = "<pre>" + "\n".join(rows) + "</pre>"
    return f"{title_line}\n{table}"


def build_pronosticos_messages(
    events: Iterable[dict],
    today_local: datetime.date,
    tz: ZoneInfo,
) -> list[tuple[str, str]]:
    """Mensajes de /pronosticos: solo partidos POR JUGAR de hoy y mañana.

    Filtra estrictamente a estado ``pre`` (no jugados ni en vivo) y los clasifica
    por fecha local en CDMX, quedándose únicamente con hoy y mañana.
    """
    tomorrow = today_local + datetime.timedelta(days=1)

    by_day: dict[datetime.date, list[dict]] = {today_local: [], tomorrow: []}
    for event in events:
        if event.get("state") != "pre" or event.get("completed"):
            continue
        event_local_day = event["date_utc"].astimezone(tz).date()
        if event_local_day in by_day:
            by_day[event_local_day].append(event)

    for day in by_day:
        by_day[day].sort(key=lambda e: e["date_utc"])

    sections = [
        ("🕒", f"Hoy · {fmt_mx_date(today_local)}", by_day[today_local]),
        ("🕗", f"Mañana · {fmt_mx_date(tomorrow)}", by_day[tomorrow]),
    ]

    total = sum(len(evs) for _, _, evs in sections)
    header = (
        "<b>🔮 Pronósticos · Mundial 2026</b>\n"
        "<i>Partidos por jugar — L: local · E: empate · V: visita</i>"
    )

    if total == 0:
        return [(f"{header}\n\n<i>No hay partidos por jugar hoy ni mañana.</i>", "HTML")]

    messages: list[tuple[str, str]] = []
    parts: list[str] = [header]

    for emoji, title, day_events in sections:
        block = _build_forecast_section(emoji, title, day_events, tz)
        candidate = "\n\n".join(parts + [block])
        if len(candidate) > TELEGRAM_MESSAGE_LIMIT and len(parts) > 0:
            messages.append(("\n\n".join(parts), "HTML"))
            parts = [block]
        else:
            parts.append(block)

    if parts:
        messages.append(("\n\n".join(parts), "HTML"))

    return messages
