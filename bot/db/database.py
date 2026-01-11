import aiosqlite
import time
from typing import Optional

class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("PRAGMA foreign_keys = ON;")
        await self.conn.execute("PRAGMA journal_mode = WAL;")
        await self.conn.execute("PRAGMA synchronous = NORMAL;")
        await self._init_schema()
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def _init_schema(self):
        # Table for user triggers
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_triggers (
                user_id INTEGER PRIMARY KEY,
                default_trigger TEXT CHECK (default_trigger IS NULL OR length(default_trigger) < 255)
            )
        """)
        await self.conn.commit()
