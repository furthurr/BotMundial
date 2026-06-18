import datetime
import logging
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from app import config, espn, formatters
from app.middleware import require_auth

logger = logging.getLogger(__name__)


@require_auth
async def pronosticos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    try:
        tz = ZoneInfo(config.DEFAULT_TIMEZONE)
        today_local = datetime.datetime.now(tz).date()

        # ESPN interpreta el parámetro `dates` en horario del Este de EE. UU., no
        # en CDMX ni UTC. Consultamos una ventana amplia (un día extra a cada
        # lado) y luego el formatter clasifica estrictamente por fecha local y se
        # queda solo con HOY y MAÑANA, en estado "pre" (por jugar).
        query_from = today_local - datetime.timedelta(days=1)
        query_to = today_local + datetime.timedelta(days=2)

        events = await espn.fetch_world_cup_scoreboard(query_from, query_to)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch World Cup scoreboard for forecasts: %s", exc, exc_info=True)
        await update.message.reply_text(
            "⚠️ No pude obtener los pronósticos en este momento. Intenta de nuevo en unos segundos."
        )
        return

    messages = formatters.build_pronosticos_messages(events, today_local, tz)
    for text, parse_mode in messages:
        await update.message.reply_text(text, parse_mode=parse_mode)
