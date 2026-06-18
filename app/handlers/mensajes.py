from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.owner import AWAITING_PASSWORD_KEY, handle_password_reply
from app.middleware import _is_owner, require_auth


@require_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    # Owner is in the middle of creating a password (conversational flow).
    if (
        update.effective_chat
        and _is_owner(update.effective_chat.id)
        and context.user_data.get(AWAITING_PASSWORD_KEY)
    ):
        await handle_password_reply(update, context)
        return

    await update.message.reply_text(
        "🤔 No entendí tu mensaje. Usa /menu para ver los comandos disponibles."
    )
