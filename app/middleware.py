import logging
import math
import time
from functools import wraps
from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from app import config, database

logger = logging.getLogger(__name__)

PUBLIC_COMMANDS = {"/start", "/menu"}


def _is_owner(chat_id: int) -> bool:
    return config.OWNER_CHAT_ID is not None and chat_id == config.OWNER_CHAT_ID


async def check_authorization(update: Update) -> bool:
    """Returns True if the update is allowed to be processed by handlers.

    Side effects:
      - Replies with a 'welcome' / 'access granted' / 'rejected' message
        when needed.
      - Stops the update via ApplicationHandlerStop when not allowed.
    """
    chat = update.effective_chat
    if chat is None:
        raise ApplicationHandlerStop()

    chat_id_int = chat.id
    chat_id_str = str(chat_id_int)

    # 1) Owner bypass.
    if _is_owner(chat_id_int):
        return True

    message = update.message
    text = (message.text.strip() if message and message.text else "")
    command = ""
    if text.startswith("/"):
        command = text.split()[0].lower().split("@")[0]

    # 2) Public commands: let /start and /menu through so the user can see the
    #    welcome message.
    if command in PUBLIC_COMMANDS:
        return True

    # 3) Already authorized?
    if await database.is_authorized(chat_id_str):
        return True

    # 4) Try the message text as a single-use access password.
    if text and not text.startswith("/"):
        user = await database.consume_password(
            text,
            chat_id_str,
            update.effective_user.username if update.effective_user else None,
            update.effective_user.first_name if update.effective_user else None,
        )
        if user is not None:
            if message:
                await message.reply_text(
                    "✅ Acceso concedido al Mundial 2026 Bot.\n"
                    "Usa /menu para ver los comandos."
                )
            logger.info("Authorized chat_id=%s via single-use password", chat_id_str)
            raise ApplicationHandlerStop()

    # 5) Reject (also covers passwords that were already used by someone else).
    if message:
        await message.reply_text(
            "🔒 Bot privado. Para usar el bot pídele tu contraseña a "
            f"@{config.OWNER_USERNAME}."
        )
    logger.info(
        "Rejected unauthorized chat_id=%s command=%s",
        chat_id_str,
        command or "<text>",
    )
    raise ApplicationHandlerStop()


def require_auth(
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]],
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]:
    """Decorator: runs authorization + rate-limit before the wrapped handler.

    Order matters: authorization runs first so unauthorized users get the
    "private bot" message, not the rate-limit "please wait" message.
    """

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Authorize first so unauthorized users always get the "private bot"
        # message instead of the rate-limit "please wait" message. The cooldown
        # only applies to already-valid users (owner is exempt inside it).
        await check_authorization(update)
        await enforce_rate_limit(update, context)
        return await handler(update, context)

    return wrapper


# --- Rate limit ------------------------------------------------------------

async def enforce_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enforces a cooldown per chat (owner exempt). Raises ApplicationHandlerStop
    to abort the handler if the user is sending requests too fast.
    """
    cooldown = config.USER_COOLDOWN_SECONDS
    if cooldown <= 0:
        return

    chat = update.effective_chat
    if chat is None:
        return

    chat_id_int = chat.id
    if _is_owner(chat_id_int):
        return

    chat_id_str = str(chat_id_int)
    last_seen: dict[str, float] = context.application.bot_data.setdefault(
        "user_last_request", {}
    )
    now = time.monotonic()
    next_allowed = float(last_seen.get(chat_id_str, 0.0))
    if now < next_allowed:
        wait = max(math.ceil(next_allowed - now), 1)
        message = update.message
        if message:
            await message.reply_text(
                f"⏳ Espera {wait} segundos antes de enviar otra solicitud."
            )
        raise ApplicationHandlerStop()

    last_seen[chat_id_str] = now + cooldown
