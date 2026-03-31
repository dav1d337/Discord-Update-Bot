import sqlite3
from typing import Any, Dict, List, Optional

class SteamDatabase:
    def __init__(self, path: str = "steam_watchlist.db"):
        self.path = path
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row

    def init_db(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_games (
                appid TEXT PRIMARY KEY,
                name TEXT,
                last_news_id TEXT,
                last_news_date INTEGER,
                last_news_title TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER
            )
            """
        )
        cursor.execute("PRAGMA table_info(tracked_games)")
        columns = {row[1] for row in cursor.fetchall()}
        if "last_news_title" not in columns:
            cursor.execute("ALTER TABLE tracked_games ADD COLUMN last_news_title TEXT")
        self.connection.commit()

    def add_game(
        self,
        appid: str,
        name: Optional[str] = None,
        last_news_id: Optional[str] = None,
        last_news_date: int = 0,
        last_news_title: Optional[str] = None,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO tracked_games (appid, name, last_news_id, last_news_date, last_news_title) VALUES (?, ?, ?, ?, ?)",
            (appid, name or "", last_news_id, last_news_date, last_news_title),
        )
        self.connection.commit()

    def remove_game(self, appid: str) -> None:
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM tracked_games WHERE appid = ?", (appid,))
        self.connection.commit()

    def get_game(self, appid: str) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM tracked_games WHERE appid = ?", (appid,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def find_games_by_name(self, query: str) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT * FROM tracked_games WHERE LOWER(name) LIKE ? ORDER BY appid",
            (f"%{query.lower()}%",),
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_games(self) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM tracked_games ORDER BY appid")
        return [dict(row) for row in cursor.fetchall()]

    def update_game_news(
        self,
        appid: str,
        last_news_id: Optional[str],
        last_news_date: int,
        last_news_title: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            "UPDATE tracked_games SET last_news_id = ?, last_news_date = ?, last_news_title = COALESCE(NULLIF(?, ''), last_news_title), name = COALESCE(NULLIF(?, ''), name) WHERE appid = ?",
            (last_news_id, last_news_date, last_news_title or "", name or "", appid),
        )
        self.connection.commit()

    def set_notification_channel(self, guild_id: int, channel_id: int) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO guild_channels (guild_id, channel_id) VALUES (?, ?)",
            (guild_id, channel_id),
        )
        self.connection.commit()

    def get_notification_channel(self, guild_id: int) -> Optional[int]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT channel_id FROM guild_channels WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def remove_notification_channel(self, guild_id: int) -> None:
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM guild_channels WHERE guild_id = ?", (guild_id,))
        self.connection.commit()
