import logging
import os

from telegram import BotCommand, BotCommandScopeChat, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from app import config, database
from app.handlers import grupos, mensajes, owner, partidos, pronosticos, start

# --- Logging setup ---------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG if os.getenv("BOTMUNDIAL_DEBUG") else getattr(logging, config.LOG_LEVEL, logging.INFO),
)
# Silence httpx INFO noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# --- Bot command menu ------------------------------------------------------

PUBLIC_COMMANDS = [
    BotCommand("start", "Mensaje de bienvenida"),
    BotCommand("menu", "Muestra el menú principal de comandos"),
    BotCommand("partidos", "Partidos de ayer, hoy y mañana del Mundial 2026"),
    BotCommand("pronosticos", "Pronóstico % de los partidos por jugar hoy y mañana"),
    BotCommand("grupos", "Tabla de posiciones de los grupos del Mundial 2026"),
]

OWNER_COMMANDS = [
    *PUBLIC_COMMANDS,
    BotCommand(
        "crearpass",
        "Crea una contraseña de un solo uso: /crearpass <contraseña>",
    ),
]


async def register_command_menu(application: Application) -> None:
    await application.bot.set_my_commands(PUBLIC_COMMANDS)

    if config.OWNER_CHAT_ID is not None:
        try:
            await application.bot.set_my_commands(
                OWNER_COMMANDS,
                scope=BotCommandScopeChat(chat_id=config.OWNER_CHAT_ID),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not register owner commands: %s", exc)
    else:
        logger.warning(
            "OWNER_CHAT_ID is empty. Owner-only commands will not be registered."
        )


# --- Bootstrap -------------------------------------------------------------


async def init() -> None:
    await database.init_db()


def main() -> None:
    if config.OWNER_CHAT_ID is None:
        logger.warning(
            "OWNER_CHAT_ID is not set. The owner won't be recognized. "
            "Set it in .env before running for real."
        )

    logger.info("Starting %s v%s...", config.BOT_NAME, config.BOT_VERSION)

    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Global error handler so nothing fails silently.
    async def _on_error(update: object, context) -> None:
        logger.error("Handler error: %s", context.error, exc_info=context.error)

    application.add_error_handler(_on_error)

    # All handlers in the default group (0). Rate limiting and auth are enforced
    # inside the handlers via decorators, so we don't need a separate group that
    # could swallow the update before it reaches the command handlers.
    application.add_handler(CommandHandler("start", start.start_command))
    application.add_handler(CommandHandler("menu", start.menu_command))
    application.add_handler(CommandHandler("partidos", partidos.partidos_command))
    application.add_handler(CommandHandler("pronosticos", pronosticos.pronosticos_command))
    application.add_handler(CommandHandler("grupos", grupos.grupos_command))
    application.add_handler(CommandHandler("crearpass", owner.crearpass_command))
    application.add_handler(CommandHandler("cancelar", owner.cancelar_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, mensajes.handle_message)
    )

    async def _post_init(app: Application) -> None:
        await init()
        await register_command_menu(app)

    application.post_init = _post_init  # type: ignore[assignment]

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
