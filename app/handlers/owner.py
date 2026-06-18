import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from app import config, database
from app.middleware import _is_owner, require_auth

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 4

# Key used in context.user_data to mark that the owner is being asked for the
# password text in a follow-up message (conversational flow).
AWAITING_PASSWORD_KEY = "awaiting_new_password"

# Matches the command prefix "/crearpass" (optionally "@BotName") and any
# leading spaces, so we can inspect the raw remainder for whitespace.
_CMD_PREFIX_RE = re.compile(r"^/crearpass(?:@\w+)?\s*", re.IGNORECASE)

# Any Unicode whitespace inside the password is rejected.
_WHITESPACE_RE = re.compile(r"\s")


@require_auth
async def crearpass_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    if not _is_owner(update.effective_chat.id):
        return  # auth already rejected; defensive double-check

    raw_text = update.message.text or ""
    # Everything after the command word, preserving inner characters.
    remainder = _CMD_PREFIX_RE.sub("", raw_text, count=1)
    secret = remainder.strip()

    # No password on the same line -> ask for it in a follow-up message.
    if not secret:
        context.user_data[AWAITING_PASSWORD_KEY] = True
        await update.message.reply_text(
            "✍️ Envíame ahora la contraseña que quieres crear.\n\n"
            "• Una sola cadena, sin espacios.\n"
            f"• Mínimo {MIN_PASSWORD_LENGTH} caracteres.\n"
            "• Será de un solo uso.\n\n"
            "Escribe /cancelar para abortar."
        )
        return

    # Password provided inline (still supported).
    await _process_new_password(update, context, secret)


@require_auth
async def cancelar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancels the pending password-creation flow (owner only)."""
    if not update.message:
        return
    if not (update.effective_chat and _is_owner(update.effective_chat.id)):
        return

    if context.user_data.pop(AWAITING_PASSWORD_KEY, None):
        await update.message.reply_text(
            "Operación cancelada. No se creó ninguna contraseña."
        )
    else:
        await update.message.reply_text("No hay ninguna operación pendiente para cancelar.")


async def handle_password_reply(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles the owner's follow-up message that contains the new password."""
    if not update.message:
        return

    text = update.message.text or ""
    secret = text.strip()

    # Allow cancelling the flow.
    if secret.lower() in {"/cancelar", "cancelar"}:
        context.user_data.pop(AWAITING_PASSWORD_KEY, None)
        await update.message.reply_text("Operación cancelada. No se creó ninguna contraseña.")
        return

    # Consume the awaiting state regardless of validity, but re-arm it on
    # recoverable validation errors so the owner can simply resend.
    context.user_data.pop(AWAITING_PASSWORD_KEY, None)
    await _process_new_password(update, context, secret, from_followup=True)


async def _process_new_password(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    secret: str,
    from_followup: bool = False,
) -> None:
    """Validates and stores a new single-use password."""

    def _rearm_if_followup() -> None:
        if from_followup:
            context.user_data[AWAITING_PASSWORD_KEY] = True

    if not secret:
        _rearm_if_followup()
        await update.message.reply_text(
            "❌ La contraseña no puede estar vacía. Envíame una cadena sin espacios."
        )
        return

    if _WHITESPACE_RE.search(secret):
        _rearm_if_followup()
        await update.message.reply_text(
            "❌ No se aceptan espacios en blanco en la contraseña.\n"
            "Envía una sola cadena sin espacios e inténtalo de nuevo."
        )
        return

    if len(secret) < MIN_PASSWORD_LENGTH:
        _rearm_if_followup()
        await update.message.reply_text(
            f"❌ La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
        )
        return

    if await database.password_exists(secret):
        _rearm_if_followup()
        await update.message.reply_text(
            "❌ Esa contraseña ya existe. Usa una diferente."
        )
        return

    owner_chat_id = config.OWNER_CHAT_ID or 0
    created = await database.create_password(secret, owner_chat_id)
    if created is None:
        _rearm_if_followup()
        await update.message.reply_text(
            "❌ Esa contraseña ya existe. Usa una diferente."
        )
        return

    await update.message.reply_text(
        f"✅ Contraseña creada: {created['secret']}\n\n"
        "Compártela con la persona que quieres autorizar.\n"
        "Cuando la escriba al bot, quedará autorizada automáticamente.\n"
        "No distingue mayúsculas de minúsculas.\n"
        "Es de un solo uso: solo el primero que la utilice obtendrá acceso."
    )
    logger.info("Owner created a new access password (id=%s)", created["id"])
