import datetime
import logging
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from app import config, espn, formatters
from app.middleware import require_auth

logger = logging.getLogger(__name__)


@require_auth
async def partidos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    try:
        tz = ZoneInfo(config.DEFAULT_TIMEZONE)
        now_local = datetime.datetime.now(tz)
        today_local = now_local.date()

        # ESPN interprets the `dates` query param in US Eastern Time, not UTC
        # nor CDMX. To make sure we capture every match that falls on
        # yesterday/today/tomorrow *in CDMX*, we query a wider window (one extra
        # day on each side) and then classify strictly by CDMX local date in the
        # formatter. This prevents matches from appearing on the wrong day or
        # being dropped at the day boundaries.
        query_from = today_local - datetime.timedelta(days=2)
        query_to = today_local + datetime.timedelta(days=2)

        events = await espn.fetch_world_cup_scoreboard(query_from, query_to)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch World Cup scoreboard: %s", exc, exc_info=True)
        await update.message.reply_text(
            "⚠️ No pude obtener los partidos en este momento. Intenta de nuevo en unos segundos."
        )
        return

    if not events:
        await update.message.reply_text(
            "No hay partidos del Mundial 2026 en las próximas fechas."
        )
        return

    messages = formatters.build_partidos_messages(events, today_local, tz)
    for text, parse_mode in messages:
        await update.message.reply_text(text, parse_mode=parse_mode)
