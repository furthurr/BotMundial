import logging

from telegram import Update
from telegram.ext import ContextTypes

from app import espn, formatters
from app.middleware import require_auth

logger = logging.getLogger(__name__)


@require_auth
async def grupos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    try:
        groups = await espn.fetch_world_cup_standings()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch World Cup standings: %s", exc, exc_info=True)
        await update.message.reply_text(
            "⚠️ No pude obtener la tabla de grupos en este momento. "
            "Intenta de nuevo en unos segundos."
        )
        return

    if not groups:
        await update.message.reply_text(
            "No hay datos de grupos del Mundial 2026 disponibles."
        )
        return

    messages = formatters.build_grupos_messages(groups)
    for text, parse_mode in messages:
        await update.message.reply_text(text, parse_mode=parse_mode)
