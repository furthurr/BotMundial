import datetime
import logging
import os
import sqlite3
import unicodedata
from typing import Any, Optional

import aiosqlite

from app import config

logger = logging.getLogger(__name__)


def normalize_secret(value: str) -> str:
    # Unicode-normalize, trim, and lowercase so passwords are case-insensitive.
    return unicodedata.normalize("NFKC", value).strip().lower()


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat()


async def init_db() -> None:
    db_dir = os.path.dirname(config.SQLITE_DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        with open(config.SQL_INIT_PATH, "r", encoding="utf-8") as f:
            sql_script = f.read()
        await db.executescript(sql_script)
        await db.commit()
    logger.info("Database initialized at %s", config.SQLITE_DB_PATH)


# --- Authorized users ------------------------------------------------------


async def is_authorized(chat_id: int | str) -> bool:
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM authorized_users WHERE chat_id = ? AND is_active = 1",
            (str(chat_id),),
        )
        row = await cursor.fetchone()
        return row is not None


async def get_user(chat_id: int | str) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            '''
            SELECT chat_id, username, first_name, secret, created_at,
                   created_by_chat_id, is_active
            FROM authorized_users
            WHERE chat_id = ?
            ''',
            (str(chat_id),),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


# --- Access passwords ------------------------------------------------------


async def password_exists(secret: str) -> bool:
    """True if an ACTIVE password with the same normalized value already exists."""
    norm = normalize_secret(secret)
    if not norm:
        return False
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM access_passwords WHERE secret_norm = ? AND is_active = 1",
            (norm,),
        )
        row = await cursor.fetchone()
        return row is not None


async def create_password(secret: str, owner_chat_id: int | str) -> Optional[dict[str, Any]]:
    """Creates a new single-use password.

    The password is stored in lowercase (normalized) so that comparison is
    case-insensitive and the stored value is always lowercase.

    Returns the created password row, or None if a password with the same
    normalized value already exists (unique constraint).
    """
    norm = normalize_secret(secret)
    # Store the lowercase form in both columns.
    stored_secret = norm
    now = _now_iso()
    try:
        async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
            cursor = await db.execute(
                '''
                INSERT INTO access_passwords (
                    secret, secret_norm, created_at, created_by_chat_id, is_active
                ) VALUES (?, ?, ?, ?, 1)
                ''',
                (stored_secret, norm, now, str(owner_chat_id)),
            )
            await db.commit()
            password_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return None

    return {
        "id": password_id,
        "secret": stored_secret,
        "secret_norm": norm,
        "created_at": now,
        "created_by_chat_id": str(owner_chat_id),
        "is_active": 1,
        "used_by_chat_id": None,
        "used_at": None,
    }


async def find_available_password(secret: str) -> Optional[dict[str, Any]]:
    """Returns an ACTIVE, UNUSED password matching the given secret, else None.

    A password is 'available' when is_active = 1 and it has not been consumed
    by any user yet (used_by_chat_id IS NULL).
    """
    norm = normalize_secret(secret)
    if not norm:
        return None
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            '''
            SELECT id, secret, secret_norm, created_at, created_by_chat_id,
                   is_active, used_by_chat_id, used_at
            FROM access_passwords
            WHERE secret_norm = ? AND is_active = 1 AND used_by_chat_id IS NULL
            ''',
            (norm,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def consume_password(
    secret: str,
    chat_id: int | str,
    username: Optional[str],
    first_name: Optional[str],
) -> Optional[dict[str, Any]]:
    """Atomically consumes an available password for the given user.

    - Marks the password as used by this chat_id.
    - Inserts/updates the user in authorized_users.

    Returns the authorized user row on success, or None if the password was not
    available (already used / inactive / nonexistent) at the moment of consuming.
    """
    norm = normalize_secret(secret)
    if not norm:
        return None

    now = _now_iso()
    chat_id_str = str(chat_id)

    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        # Atomic claim: only succeeds if still unused.
        cursor = await db.execute(
            '''
            UPDATE access_passwords
            SET used_by_chat_id = ?, used_at = ?
            WHERE secret_norm = ? AND is_active = 1 AND used_by_chat_id IS NULL
            ''',
            (chat_id_str, now, norm),
        )
        if cursor.rowcount == 0:
            await db.rollback()
            return None

        # Find the owner who created this password (for created_by_chat_id).
        owner_cursor = await db.execute(
            "SELECT created_by_chat_id, secret FROM access_passwords WHERE secret_norm = ?",
            (norm,),
        )
        owner_row = await owner_cursor.fetchone()
        created_by = owner_row[0] if owner_row else str(config.OWNER_CHAT_ID or 0)
        stored_secret = owner_row[1] if owner_row else secret

        await db.execute(
            '''
            INSERT INTO authorized_users (
                chat_id, username, first_name, secret,
                created_at, created_by_chat_id, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET
                username = COALESCE(excluded.username, authorized_users.username),
                first_name = COALESCE(excluded.first_name, authorized_users.first_name),
                secret = excluded.secret,
                is_active = 1
            ''',
            (chat_id_str, username, first_name, stored_secret, now, created_by),
        )
        await db.commit()

    return await get_user(chat_id_str)
