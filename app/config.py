import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it in .env before starting the bot."
        )
    return value


def _optional_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r, using default %s", name, raw, default)
        return default


# --- Telegram ---
TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")

OWNER_CHAT_ID_RAW: str = os.getenv("OWNER_CHAT_ID", "").strip()
OWNER_CHAT_ID: int | None = int(OWNER_CHAT_ID_RAW) if OWNER_CHAT_ID_RAW else None
OWNER_USERNAME: str = os.getenv("OWNER_USERNAME", "pedroGVFurthurr").strip() or "pedroGVFurthurr"

USER_COOLDOWN_SECONDS: int = _optional_int("USER_COOLDOWN_SECONDS", 10)

# --- Persistence ---
SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", "data/bot.db").strip() or "data/bot.db"
SQL_INIT_PATH: str = os.getenv("SQL_INIT_PATH", "sql/init.sql").strip() or "sql/init.sql"

# --- Logging ---
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

# --- ESPN ---
DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "America/Mexico_City").strip() or "America/Mexico_City"
ESPN_BASE_URL: str = os.getenv(
    "ESPN_BASE_URL",
    "https://site.api.espn.com/apis/site/v2/sports/soccer",
).strip().rstrip("/")
# Standings live under a different ESPN path than the scoreboard.
ESPN_STANDINGS_BASE_URL: str = os.getenv(
    "ESPN_STANDINGS_BASE_URL",
    "https://site.api.espn.com/apis/v2/sports/soccer",
).strip().rstrip("/")
ESPN_LEAGUE_SLUG: str = os.getenv("ESPN_LEAGUE_SLUG", "fifa.world").strip() or "fifa.world"
ESPN_WORLD_CUP_FILTER_REGEX: str = os.getenv(
    "ESPN_WORLD_CUP_FILTER_REGEX", "fifa|world cup|mundial"
).strip() or "fifa|world cup|mundial"
ESPN_REQUEST_TIMEOUT_SECONDS: int = _optional_int("ESPN_REQUEST_TIMEOUT_SECONDS", 10)
ESPN_CACHE_TTL_SECONDS: int = _optional_int("ESPN_CACHE_TTL_SECONDS", 60)

# --- Bot meta ---
BOT_NAME: str = "BotMundial"
BOT_VERSION: str = "0.1.0"
