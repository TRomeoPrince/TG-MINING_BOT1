from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import aiosqlite


@dataclass
class UserState:
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    balance: float
    referrer_id: Optional[int]
    mining_started_at: Optional[int]
    mining_ends_at: Optional[int]
    referral_rewarded: bool


class Database:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance REAL NOT NULL DEFAULT 0,
                    referrer_id INTEGER,
                    mining_started_at INTEGER,
                    mining_ends_at INTEGER,
                    referral_rewarded INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (referrer_id) REFERENCES users(telegram_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    entry_type TEXT NOT NULL,
                    note TEXT,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                )
            """)
            await db.commit()

    async def ensure_user(
        self,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        referrer_id: Optional[int] = None,
    ) -> bool:
        """Create user if new. Returns True only when a new user is created."""
        if referrer_id == telegram_id:
            referrer_id = None

        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT telegram_id FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            exists = await cur.fetchone()
            if exists:
                await db.execute(
                    "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
                    (username, first_name, telegram_id),
                )
                await db.commit()
                return False

            valid_referrer = None
            if referrer_id is not None:
                cur = await db.execute(
                    "SELECT telegram_id FROM users WHERE telegram_id = ?",
                    (referrer_id,),
                )
                if await cur.fetchone():
                    valid_referrer = referrer_id

            await db.execute(
                """
                INSERT INTO users (
                    telegram_id, username, first_name, balance, referrer_id,
                    mining_started_at, mining_ends_at, referral_rewarded, created_at
                ) VALUES (?, ?, ?, 0, ?, NULL, NULL, 0, ?)
                """,
                (telegram_id, username, first_name, valid_referrer, int(time.time())),
            )
            await db.commit()
            return True

    async def get_user(self, telegram_id: int) -> Optional[UserState]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                SELECT telegram_id, username, first_name, balance, referrer_id,
                       mining_started_at, mining_ends_at, referral_rewarded
                FROM users WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return UserState(
                telegram_id=row[0], username=row[1], first_name=row[2], balance=row[3],
                referrer_id=row[4], mining_started_at=row[5], mining_ends_at=row[6],
                referral_rewarded=bool(row[7]),
            )

    async def start_mining(self, telegram_id: int, duration_seconds: int) -> tuple[bool, int]:
        now = int(time.time())
        user = await self.get_user(telegram_id)
        if not user:
            raise ValueError("User does not exist")

        if user.mining_ends_at is not None:
            return False, user.mining_ends_at

        ends_at = now + duration_seconds
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET mining_started_at = ?, mining_ends_at = ? WHERE telegram_id = ?",
                (now, ends_at, telegram_id),
            )
            await db.commit()
        return True, ends_at

    async def claim_mining(
        self,
        telegram_id: int,
        rate_per_hour: float,
        referral_reward: float,
    ) -> tuple[str, float, Optional[int]]:
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                """
                SELECT balance, referrer_id, mining_started_at, mining_ends_at, referral_rewarded
                FROM users WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
            row = await cur.fetchone()
            if not row:
                await db.rollback()
                return "missing", 0.0, None

            balance, referrer_id, started_at, ends_at, referral_rewarded = row
            if started_at is None or ends_at is None:
                await db.rollback()
                return "not_started", 0.0, None
            if now < ends_at:
                await db.rollback()
                return "not_ready", float(ends_at - now), None

            hours = max(0.0, (ends_at - started_at) / 3600.0)
            mined = round(hours * rate_per_hour, 8)

            await db.execute(
                """
                UPDATE users
                SET balance = balance + ?, mining_started_at = NULL, mining_ends_at = NULL
                WHERE telegram_id = ?
                """,
                (mined, telegram_id),
            )
            await db.execute(
                "INSERT INTO ledger (telegram_id, amount, entry_type, note, created_at) VALUES (?, ?, ?, ?, ?)",
                (telegram_id, mined, "mining_claim", "Completed mining session", now),
            )

            rewarded_referrer = None
            if referrer_id is not None and not bool(referral_rewarded):
                await db.execute(
                    "UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
                    (referral_reward, referrer_id),
                )
                await db.execute(
                    "UPDATE users SET referral_rewarded = 1 WHERE telegram_id = ?",
                    (telegram_id,),
                )
                await db.execute(
                    "INSERT INTO ledger (telegram_id, amount, entry_type, note, created_at) VALUES (?, ?, ?, ?, ?)",
                    (referrer_id, referral_reward, "referral_reward", f"Qualified referral {telegram_id}", now),
                )
                rewarded_referrer = referrer_id

            await db.commit()
            return "claimed", mined, rewarded_referrer

    async def referral_count(self, telegram_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM users WHERE referrer_id = ?",
                (telegram_id,),
            )
            row = await cur.fetchone()
            return int(row[0] if row else 0)

    async def qualified_referral_count(self, telegram_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM users WHERE referrer_id = ? AND referral_rewarded = 1",
                (telegram_id,),
            )
            row = await cur.fetchone()
            return int(row[0] if row else 0)
