# TG Mining Bot

Telegram mining/rewards bot MVP.

This project is a **Telegram bot + planned Telegram Mini App**. The current mining engine accrues internal reward points over timed sessions. It does **not** perform proof-of-work mining on a user's phone or computer.

## Current MVP

- Telegram `/start` onboarding
- Referral links using `?start=ref_<telegram_id>`
- 8-hour mining sessions
- Server-side timestamp calculation
- Claim/restart flow
- Balance display
- Referral statistics
- One-time referral reward after an invitee completes their first mining session
- SQLite persistence
- Transaction ledger for mining and referral rewards
- Inline Telegram buttons

## Commands

- `/start` — create/open account
- `/mine` — start or check mining
- `/claim` — claim a completed session
- `/balance` — view balance and referral statistics
- `/referral` — get your invite link
- `/help` — show help

## Default economics

Configured in `.env`:

- Session duration: **8 hours**
- Base rate: **100 MIN/hour**
- Referral reward: **500 MIN**

These are development defaults and can be changed without editing the bot source.

## Run locally

### 1. Clone the repository

```bash
git clone https://github.com/TRomeoPrince/TG-MINING_BOT1.git
cd TG-MINING_BOT1
```

### 2. Create a virtual environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the bot

Copy:

```text
.env.example
```

to:

```text
.env
```

Then replace:

```text
BOT_TOKEN=replace_with_botfather_token
```

with the token from BotFather.

### 5. Start the bot

```bash
python -m app.bot
```

## Project structure

```text
TG-MINING_BOT1/
├── app/
│   ├── __init__.py
│   ├── bot.py
│   ├── config.py
│   └── db.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Next build phase

1. Telegram Mini App dashboard
2. Live mining countdown UI
3. Tasks and verification
4. Mining boosts and levels
5. Leaderboards
6. Admin panel
7. Anti-abuse controls
8. PostgreSQL production migration
9. Reward/withdrawal ledger
