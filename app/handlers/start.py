from telegram import Update
from telegram.ext import ContextTypes

from app import config
from app.middleware import require_auth

WELCOME_TEXT = (
    "👋 Bienvenido al BotMundial.\n\n"
    "Este es un bot privado que muestra los partidos del Mundial 2026 "
    "consumiendo datos en vivo de ESPN.\n\n"
    "📋 Comandos disponibles:\n"
    "/start - Muestra este mensaje de bienvenida.\n"
    "/menu - Muestra el menú principal de comandos.\n"
    "/partidos - Muestra los partidos de ayer, hoy y mañana del Mundial 2026.\n"
    "/pronosticos - Muestra el pronóstico % de los partidos por jugar hoy y mañana.\n"
    "/grupos - Muestra la tabla de posiciones de los grupos del Mundial 2026.\n\n"
    f"🔐 Si aún no tienes acceso, pídele tu contraseña a @{config.OWNER_USERNAME}."
)


@require_auth
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(WELCOME_TEXT)


@require_auth
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(WELCOME_TEXT)
