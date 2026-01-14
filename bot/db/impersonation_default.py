from bot.db.database import Database, db

class ImpersonationDefaultRepo:
    def __init__(self, database: Database):
        self.database = database

    async def init_schema(self) -> None:
        await self.database.execute("""
            CREATE TABLE IF NOT EXISTS user_triggers (
                user_id INTEGER PRIMARY KEY,
                default_trigger TEXT CHECK (default_trigger IS NULL OR length(default_trigger) < 255)
            )
        """)

    async def get(self, user_id: int) -> str | None:
        """Return the user's default trigger, or None if not set."""
        row = await self.database.execute_fetchone(
            "SELECT default_trigger FROM user_triggers WHERE user_id = ?",
            (user_id,)
        )
        return row[0] if row else None

    async def set(self, user_id: int, trigger: str) -> None:
        """
        Set or update the user's default trigger.
        Creates a row if it doesn't exist.
        """
        await self.database.execute(
            """
            INSERT INTO user_triggers (user_id, default_trigger)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET default_trigger = excluded.default_trigger
            """,
            (user_id, trigger)
        )

    async def unset(self, user_id: int) -> None:
        """
        Unset the user's default trigger (sets to NULL).
        Creates a row if it doesn't exist to avoid errors.
        """
        # Ensure a row exists
        await self.database.execute(
            "INSERT OR IGNORE INTO user_triggers (user_id) VALUES (?)",
            (user_id,)
        )
        # Set default_trigger to NULL
        await self.database.execute(
            "UPDATE user_triggers SET default_trigger = NULL WHERE user_id = ?",
            (user_id,)
        )

impersonation_default: ImpersonationDefaultRepo = ImpersonationDefaultRepo(database=db)
