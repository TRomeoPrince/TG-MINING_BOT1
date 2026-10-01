import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: str
    mining_session_hours: int
    mining_rate_per_hour: float
    referral_reward: float


def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Copy .env.example to .env and add your BotFather token.")

    return Settings(
        bot_token=token,
        db_path=os.getenv("DB_PATH", "mining_bot.db"),
        mining_session_hours=int(os.getenv("MINING_SESSION_HOURS", "8")),
        mining_rate_per_hour=float(os.getenv("MINING_RATE_PER_HOUR", "100")),
        referral_reward=float(os.getenv("REFERRAL_REWARD", "500")),
    )
