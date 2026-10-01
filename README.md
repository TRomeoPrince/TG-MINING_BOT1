# TG Mining Bot

Telegram mining/rewards bot MVP.

This project is being built as a **Telegram Mini App + Telegram bot**. The “mining” engine accrues internal reward points over timed sessions; it is not device proof-of-work mining.

## MVP goals

- Telegram `/start` onboarding
- Referral tracking through `?start=ref_<telegram_id>`
- 8-hour mining sessions
- Server-side balance calculation
- Claim/restart flow
- Telegram Mini App dashboard
- One-time referral reward when an invitee completes their first mining session
- SQLite for local development, with an easy path to PostgreSQL for production

More features (tasks, levels, boosts, admin tools, anti-fraud, wallets and withdrawals) will be added after the core mining engine is stable.
