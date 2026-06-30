"""
SQLite asosida ko'p foydalanuvchili (multi-tenant) saqlash qatlami.

Har bir Telegram kanal — alohida yozuv, o'z egasi (owner_user_id) va o'z
sozlamalari (mavzu, uslub, avtopost) bilan. Bitta foydalanuvchi bir nechta
kanalni ulashi va ular orasida /select orqali almashishi mumkin.
"""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from config import DB_FILE, DEFAULT_CHANNEL_SETTINGS

_lock = threading.Lock()


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _lock, _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                channel_id      INTEGER PRIMARY KEY,
                username        TEXT,
                title           TEXT,
                owner_user_id   INTEGER NOT NULL,
                topic           TEXT NOT NULL,
                tone            TEXT NOT NULL,
                language        TEXT NOT NULL,
                autopost_enabled INTEGER NOT NULL DEFAULT 0,
                interval_hours  INTEGER NOT NULL DEFAULT 4,
                hashtags        INTEGER NOT NULL DEFAULT 1,
                emoji           INTEGER NOT NULL DEFAULT 1,
                post_length     TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id           INTEGER PRIMARY KEY,
                active_channel_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id  INTEGER NOT NULL,
                text        TEXT NOT NULL,
                source      TEXT NOT NULL,
                timestamp   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_history_channel ON history(channel_id);
            CREATE INDEX IF NOT EXISTS idx_channels_owner ON channels(owner_user_id);
            """
        )


# ---------- Foydalanuvchi / faol kanal ----------

def ensure_user(user_id: int):
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, active_channel_id) VALUES (?, NULL)",
            (user_id,),
        )


def set_active_channel(user_id: int, channel_id: int):
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO users (user_id, active_channel_id) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET active_channel_id = excluded.active_channel_id",
            (user_id, channel_id),
        )


def get_active_channel(user_id: int) -> dict | None:
    with _lock, _conn() as conn:
        row = conn.execute(
            """
            SELECT c.* FROM channels c
            JOIN users u ON u.active_channel_id = c.channel_id
            WHERE u.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


# ---------- Kanallar ----------

def add_channel(channel_id: int, username: str | None, title: str, owner_user_id: int) -> dict:
    with _lock, _conn() as conn:
        existing = conn.execute(
            "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE channels SET username = ?, title = ? WHERE channel_id = ?",
                (username, title, channel_id),
            )
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            return dict(row)

        d = DEFAULT_CHANNEL_SETTINGS
        conn.execute(
            """
            INSERT INTO channels (
                channel_id, username, title, owner_user_id, topic, tone, language,
                autopost_enabled, interval_hours, hashtags, emoji, post_length, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel_id, username, title, owner_user_id,
                d["topic"], d["tone"], d["language"],
                d["autopost_enabled"], d["interval_hours"],
                d["hashtags"], d["emoji"], d["post_length"],
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        row = conn.execute(
            "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        return dict(row)


def get_channel(channel_id: int) -> dict | None:
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        return dict(row) if row else None


def list_user_channels(user_id: int) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM channels WHERE owner_user_id = ? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_all_autopost_channels() -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM channels WHERE autopost_enabled = 1"
        ).fetchall()
        return [dict(r) for r in rows]


def remove_channel(channel_id: int, owner_user_id: int) -> bool:
    with _lock, _conn() as conn:
        cur = conn.execute(
            "DELETE FROM channels WHERE channel_id = ? AND owner_user_id = ?",
            (channel_id, owner_user_id),
        )
        conn.execute(
            "UPDATE users SET active_channel_id = NULL "
            "WHERE active_channel_id = ?",
            (channel_id,),
        )
        return cur.rowcount > 0


def update_channel_settings(channel_id: int, **kwargs) -> dict:
    if not kwargs:
        return get_channel(channel_id)
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [channel_id]
    with _lock, _conn() as conn:
        conn.execute(f"UPDATE channels SET {cols} WHERE channel_id = ?", values)
        row = conn.execute(
            "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        return dict(row)


# ---------- Post tarixi ----------

def add_history_entry(channel_id: int, text: str, source: str = "auto"):
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO history (channel_id, text, source, timestamp) VALUES (?, ?, ?, ?)",
            (channel_id, text, source, datetime.now().isoformat(timespec="seconds")),
        )
        conn.execute(
            """
            DELETE FROM history WHERE id IN (
                SELECT id FROM history WHERE channel_id = ?
                ORDER BY id DESC LIMIT -1 OFFSET 200
            )
            """,
            (channel_id,),
        )


def get_history(channel_id: int, limit: int = 10) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM history WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
            (channel_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_recent_topics_text(channel_id: int, limit: int = 8) -> str:
    """Gemini'ga oxirgi postlar haqida qisqa kontekst berish uchun, takrorlanmaslik maqsadida."""
    entries = get_history(channel_id, limit)
    if not entries:
        return "Hozircha postlar yo'q."
    lines = []
    for e in entries:
        snippet = e["text"][:80].replace("\n", " ")
        lines.append(f"- {snippet}...")
    return "\n".join(lines)


def stats() -> dict:
    with _lock, _conn() as conn:
        total_channels = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_posts = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        autopost_on = conn.execute(
            "SELECT COUNT(*) FROM channels WHERE autopost_enabled = 1"
        ).fetchone()[0]
        return {
            "channels": total_channels,
            "users": total_users,
            "posts": total_posts,
            "autopost_on": autopost_on,
        }

