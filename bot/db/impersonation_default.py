from bot.db.database import Database

class ImpersonationDefaultRepo:
    def __init__(self, db: Database):
        if db.conn is None:
            raise RuntimeError("Database is not connected")
        self.db = db

    async def init_schema(self) -> None:
        await self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_triggers (
                user_id INTEGER PRIMARY KEY,
                default_trigger TEXT CHECK (default_trigger IS NULL OR length(default_trigger) < 255)
            )
        """)
        await self.db.conn.commit()

    async def get(self, user_id: int) -> str | None:
        """Return the user's default trigger, or None if not set."""
        async with self.db.conn.execute(
            "SELECT default_trigger FROM user_triggers WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return row[0]  # default_trigger or None

    async def set(self, user_id: int, trigger: str):
        """
        Set or update the user's default trigger.
        Creates a row if it doesn't exist.
        """
        await self.db.conn.execute(
            """
            INSERT INTO user_triggers (user_id, default_trigger)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET default_trigger = excluded.default_trigger
            """,
            (user_id, trigger)
        )
        await self.db.conn.commit()

    async def unset(self, user_id: int):
        """
        Unset the user's default trigger (sets to NULL).
        Creates a row if it doesn't exist to avoid errors.
        """
        # Ensure a row exists
        await self.db.conn.execute(
            "INSERT OR IGNORE INTO user_triggers (user_id) VALUES (?)",
            (user_id,)
        )
        # Set default_trigger to NULL
        await self.db.conn.execute(
            "UPDATE user_triggers SET default_trigger = NULL WHERE user_id = ?",
            (user_id,)
        )
        await self.db.conn.commit()
