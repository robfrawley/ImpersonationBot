import time
from bot.db.database import Database

class ImpersonationHistoryRepo:
    def __init__(self, db: Database):
        if db.conn is None:
            raise RuntimeError("Database is not connected")
        self.db = db

    async def init_schema(self) -> None:
        await self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS impersonation_history (
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, message_id)
            )
        """)
        await self.db.conn.commit()

    async def add(self, user_id: int, message_id: int) -> None:
        """Track an impersonated message."""
        await self.db.conn.execute(
            """
            INSERT OR IGNORE INTO impersonation_history
            (user_id, message_id, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, message_id, int(time.time())),
        )
        await self.db.conn.commit()

    async def has(self, user_id: int, message_id: int) -> bool:
        """Check if a message is tracked for a user."""
        async with self.db.conn.execute(
            """
            SELECT 1
            FROM impersonation_history
            WHERE user_id = ? AND message_id = ?
            """,
            (user_id, message_id),
        ) as cursor:
            return await cursor.fetchone() is not None
