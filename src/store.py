import sqlite3
from contextlib import closing
from datetime import datetime


class Store:
    def __init__(self, path: str):
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS message_cache (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                sender_id INTEGER,
                sender_name TEXT,
                text TEXT,
                media TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                chat_name TEXT,
                message_id INTEGER,
                sender_id INTEGER,
                sender_name TEXT,
                old_text TEXT,
                new_text TEXT,
                media TEXT,
                occurred_at TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def cache_message(
        self,
        chat_id: int,
        message_id: int,
        sender_id: int | None,
        sender_name: str,
        text: str | None,
        media: str | None,
    ) -> None:
        with closing(self.connection.cursor()) as cursor:
            cursor.execute(
                """
                INSERT INTO message_cache
                    (chat_id, message_id, sender_id, sender_name, text, media, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, message_id) DO UPDATE SET
                    sender_id=excluded.sender_id,
                    sender_name=excluded.sender_name,
                    text=excluded.text,
                    media=excluded.media,
                    updated_at=excluded.updated_at
                """,
                (
                    chat_id,
                    message_id,
                    sender_id,
                    sender_name,
                    text,
                    media,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        self.connection.commit()

    def get_message(self, chat_id: int, message_id: int) -> sqlite3.Row | None:
        self.connection.row_factory = sqlite3.Row
        with closing(self.connection.cursor()) as cursor:
            cursor.execute(
                "SELECT * FROM message_cache WHERE chat_id=? AND message_id=?",
                (chat_id, message_id),
            )
            return cursor.fetchone()

    def add_notice(self, **values) -> int:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        cursor = self.connection.execute(
            f"INSERT INTO notices ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_notice(self, notice_id: int) -> sqlite3.Row | None:
        self.connection.row_factory = sqlite3.Row
        with closing(self.connection.cursor()) as cursor:
            cursor.execute("SELECT * FROM notices WHERE id=?", (notice_id,))
            return cursor.fetchone()

    def get_setting(self, key: str, default: str = "") -> str:
        with closing(self.connection.cursor()) as cursor:
            cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.connection.commit()
