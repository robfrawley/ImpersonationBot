import time
from bot.db.database import Database, db

class ImpersonationHistoryRepo:
    def __init__(self, db: Database):
        self.db = db

    async def init_schema(self) -> None:
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS impersonation_history (
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, message_id)
            )
            """
        )

    async def add(self, user_id: int, message_id: int) -> None:
        """Track an impersonated message."""
        await self.db.execute(
            """
            INSERT OR IGNORE INTO impersonation_history
            (user_id, message_id, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, message_id, int(time.time())),
        )

    async def has(self, user_id: int, message_id: int) -> bool:
        """Check if a message is tracked for a user."""
        row = await self.db.execute_fetchone(
            """
            SELECT 1
            FROM impersonation_history
            WHERE user_id = ? AND message_id = ?
            """,
            (user_id, message_id),
        )
        return row is not None

impersonation_history: ImpersonationHistoryRepo = ImpersonationHistoryRepo(db)
