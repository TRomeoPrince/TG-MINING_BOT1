from __future__ import annotations

import asyncio
import time

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from .config import get_settings
from .db import Database

settings = get_settings()
db = Database(settings.db_path)
dp = Dispatcher()


def dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⛏ Mine", callback_data="mine"),
            InlineKeyboardButton(text="💰 Balance", callback_data="balance"),
        ],
        [
            InlineKeyboardButton(text="👥 Friends", callback_data="referral"),
            InlineKeyboardButton(text="🎯 Tasks", callback_data="tasks"),
        ],
        [
            InlineKeyboardButton(text="🏆 Leaderboard", callback_data="leaderboard"),
            InlineKeyboardButton(text="👛 Wallet", callback_data="wallet"),
        ],
        [InlineKeyboardButton(text="❓ Help", callback_data="help")],
    ])


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Home", callback_data="home")]]
    )


def mining_keyboard(state: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if state == "idle":
        rows.append([InlineKeyboardButton(text="⛏ Start Mining", callback_data="mine_start")])
    elif state == "active":
        rows.append([InlineKeyboardButton(text="🔄 Refresh", callback_data="mine")])
    elif state == "complete":
        rows.append([InlineKeyboardButton(text="🎁 Claim Reward", callback_data="claim")])

    rows.append([InlineKeyboardButton(text="🏠 Home", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


async def ensure_user(user: User) -> None:
    await db.ensure_user(user.id, user.username, user.first_name)


async def render(message: Message, text: str, keyboard: InlineKeyboardMarkup, edit: bool = False) -> None:
    if edit:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


async def dashboard_text(user: User) -> str:
    await ensure_user(user)
    state = await db.get_user(user.id)
    total_refs = await db.referral_count(user.id)

    mining_line = "⚪ Not mining"
    if state and state.mining_ends_at is not None:
        now = int(time.time())
        if now >= state.mining_ends_at:
            mining_line = "🟢 Ready to claim"
        else:
            mining_line = f"🟡 Mining • {format_seconds(state.mining_ends_at - now)} left"

    name = user.first_name or "Miner"
    return (
        f"⛏ <b>TG MINING</b>\n\n"
        f"Welcome, <b>{name}</b> 👋\n\n"
        f"💰 Balance: <b>{state.balance:g} MIN</b>\n"
        f"⚡ Rate: <b>{settings.mining_rate_per_hour:g} MIN/hour</b>\n"
        f"⏱ Session: <b>{settings.mining_session_hours} hours</b>\n"
        f"👥 Friends: <b>{total_refs}</b>\n"
        f"⛏ Status: <b>{mining_line}</b>\n\n"
        "Choose what you want to do:"
    )


async def show_home(user: User, target: Message, edit: bool = False) -> None:
    await render(target, await dashboard_text(user), dashboard_keyboard(), edit)


async def show_mining(user: User, target: Message, edit: bool = False) -> None:
    await ensure_user(user)
    state = await db.get_user(user.id)
    now = int(time.time())

    if state.mining_ends_at is None:
        estimated = settings.mining_rate_per_hour * settings.mining_session_hours
        text = (
            "⛏ <b>MINING CENTER</b>\n\n"
            "Status: <b>Not mining</b>\n"
            f"Rate: <b>{settings.mining_rate_per_hour:g} MIN/hour</b>\n"
            f"Session: <b>{settings.mining_session_hours} hours</b>\n"
            f"Full-session reward: <b>{estimated:g} MIN</b>\n\n"
            "Press <b>Start Mining</b> when you're ready."
        )
        await render(target, text, mining_keyboard("idle"), edit)
        return

    if now >= state.mining_ends_at:
        reward = settings.mining_rate_per_hour * settings.mining_session_hours
        text = (
            "✅ <b>MINING COMPLETE</b>\n\n"
            f"Reward waiting: <b>{reward:g} MIN</b>\n\n"
            "Claim it, then you can start another session."
        )
        await render(target, text, mining_keyboard("complete"), edit)
        return

    remaining = state.mining_ends_at - now
    elapsed = settings.mining_session_hours * 3600 - remaining
    accrued = max(0.0, elapsed / 3600 * settings.mining_rate_per_hour)
    text = (
        "⛏ <b>MINING IN PROGRESS</b>\n\n"
        f"🟢 Status: <b>Active</b>\n"
        f"⚡ Rate: <b>{settings.mining_rate_per_hour:g} MIN/hour</b>\n"
        f"🪙 Accrued: <b>{accrued:.2f} MIN</b>\n"
        f"⏳ Remaining: <b>{format_seconds(remaining)}</b>\n\n"
        "You can close Telegram. The server keeps track of the session."
    )
    await render(target, text, mining_keyboard("active"), edit)


async def start_mining(user: User, target: Message, edit: bool = False) -> None:
    await ensure_user(user)
    duration_seconds = settings.mining_session_hours * 3600
    started, _ = await db.start_mining(user.id, duration_seconds)

    if not started:
        await show_mining(user, target, edit)
        return

    estimated = settings.mining_rate_per_hour * settings.mining_session_hours
    text = (
        "🚀 <b>MINING STARTED</b>\n\n"
        f"⚡ Rate: <b>{settings.mining_rate_per_hour:g} MIN/hour</b>\n"
        f"⏱ Session: <b>{settings.mining_session_hours} hours</b>\n"
        f"🎯 Expected reward: <b>{estimated:g} MIN</b>\n\n"
        "Your session is now active."
    )
    await render(target, text, mining_keyboard("active"), edit)


async def show_balance(user: User, target: Message, edit: bool = False) -> None:
    await ensure_user(user)
    state = await db.get_user(user.id)
    total_refs = await db.referral_count(user.id)
    qualified = await db.qualified_referral_count(user.id)

    text = (
        "💰 <b>MY ACCOUNT</b>\n\n"
        f"🪙 Balance: <b>{state.balance:g} MIN</b>\n"
        f"👥 Total referrals: <b>{total_refs}</b>\n"
        f"✅ Qualified referrals: <b>{qualified}</b>\n\n"
        "Mining and referral rewards are recorded in the server ledger."
    )
    await render(target, text, home_keyboard(), edit)


async def show_referral(user: User, target: Message, bot: Bot, edit: bool = False) -> None:
    await ensure_user(user)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user.id}"
    total = await db.referral_count(user.id)
    qualified = await db.qualified_referral_count(user.id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Share Invite", url=f"https://t.me/share/url?url={link}")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="home")],
    ])

    text = (
        "👥 <b>FRIENDS</b>\n\n"
        f"🎁 Reward: <b>{settings.referral_reward:g} MIN</b> per qualified referral\n"
        f"👤 Invited: <b>{total}</b>\n"
        f"✅ Qualified: <b>{qualified}</b>\n\n"
        "<b>Your invite link</b>\n"
        f"<code>{link}</code>\n\n"
        "A referral qualifies after completing their first mining session."
    )
    await render(target, text, keyboard, edit)


async def show_tasks(user: User, target: Message, edit: bool = False) -> None:
    await ensure_user(user)
    text = (
        "🎯 <b>TASK CENTER</b>\n\n"
        "Tasks will let miners earn extra MIN for verified actions.\n\n"
        "Planned task types:\n"
        "• Daily check-in\n"
        "• Join Telegram channels\n"
        "• Referral milestones\n"
        "• Promotional partner tasks\n\n"
        "Task rewards are not enabled yet."
    )
    await render(target, text, home_keyboard(), edit)


async def show_leaderboard(user: User, target: Message, edit: bool = False) -> None:
    await ensure_user(user)
    rows = await db.top_users(10)

    if not rows:
        body = "No miners yet."
    else:
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for index, (_, username, first_name, balance) in enumerate(rows, start=1):
            prefix = medals[index - 1] if index <= 3 else f"{index}."
            name = f"@{username}" if username else (first_name or "Miner")
            lines.append(f"{prefix} {name} — <b>{balance:g} MIN</b>")
        body = "\n".join(lines)

    text = f"🏆 <b>LEADERBOARD</b>\n\n{body}"
    await render(target, text, home_keyboard(), edit)


async def show_wallet(user: User, target: Message, edit: bool = False) -> None:
    await ensure_user(user)
    state = await db.get_user(user.id)
    text = (
        "👛 <b>WALLET</b>\n\n"
        f"Available internal balance: <b>{state.balance:g} MIN</b>\n\n"
        "Withdrawals are <b>not enabled yet</b>. MIN is currently an internal reward point. "
        "We'll only enable withdrawals after the reward economics and payout method are configured."
    )
    await render(target, text, home_keyboard(), edit)


async def show_help(user: User, target: Message, edit: bool = False) -> None:
    await ensure_user(user)
    text = (
        "❓ <b>HOW IT WORKS</b>\n\n"
        "1️⃣ Start a mining session\n"
        "2️⃣ The server tracks the elapsed time\n"
        "3️⃣ Claim when the session finishes\n"
        "4️⃣ Invite friends for referral rewards\n"
        "5️⃣ Climb the leaderboard\n\n"
        "MIN is simulated reward accrual, not proof-of-work mining on your device."
    )
    await render(target, text, home_keyboard(), edit)


async def do_claim(user: User, target: Message, bot: Bot, edit: bool = False) -> None:
    await ensure_user(user)
    status, value, rewarded_referrer = await db.claim_mining(
        telegram_id=user.id,
        rate_per_hour=settings.mining_rate_per_hour,
        referral_reward=settings.referral_reward,
    )

    if status == "not_started":
        await show_mining(user, target, edit)
        return

    if status == "not_ready":
        text = (
            "⏳ <b>NOT READY YET</b>\n\n"
            f"Time remaining: <b>{format_seconds(int(value))}</b>"
        )
        await render(target, text, mining_keyboard("active"), edit)
        return

    if status == "missing":
        await render(target, "Run /start first.", home_keyboard(), edit)
        return

    state = await db.get_user(user.id)
    text = (
        "🎉 <b>REWARD CLAIMED</b>\n\n"
        f"Added: <b>+{value:g} MIN</b>\n"
        f"New balance: <b>{state.balance:g} MIN</b>\n\n"
        "Ready for another mining session?"
    )
    await render(target, text, mining_keyboard("idle"), edit)

    if rewarded_referrer is not None:
        try:
            await bot.send_message(
                rewarded_referrer,
                "👥 <b>Referral qualified!</b>\n\n"
                f"Reward: <b>+{settings.referral_reward:g} MIN</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    user = message.from_user
    referrer_id = None

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        raw = parts[1][4:]
        if raw.isdigit():
            referrer_id = int(raw)

    created = await db.ensure_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        referrer_id=referrer_id,
    )

    text = await dashboard_text(user)
    if created and referrer_id:
        text += "\n\n✅ Referral recorded."

    await message.answer(text, parse_mode="HTML", reply_markup=dashboard_keyboard())


@dp.message(Command("menu"))
async def menu_command(message: Message) -> None:
    await show_home(message.from_user, message)


@dp.message(Command("mine"))
async def mine_command(message: Message) -> None:
    await show_mining(message.from_user, message)


@dp.message(Command("claim"))
async def claim_command(message: Message, bot: Bot) -> None:
    await do_claim(message.from_user, message, bot)


@dp.message(Command("balance"))
async def balance_command(message: Message) -> None:
    await show_balance(message.from_user, message)


@dp.message(Command("referral"))
async def referral_command(message: Message, bot: Bot) -> None:
    await show_referral(message.from_user, message, bot)


@dp.message(Command("leaderboard"))
async def leaderboard_command(message: Message) -> None:
    await show_leaderboard(message.from_user, message)


@dp.message(Command("help"))
async def help_command(message: Message) -> None:
    await show_help(message.from_user, message)


@dp.callback_query(F.data == "home")
async def home_callback(query: CallbackQuery) -> None:
    await query.answer()
    await show_home(query.from_user, query.message, True)


@dp.callback_query(F.data == "mine")
async def mine_callback(query: CallbackQuery) -> None:
    await query.answer()
    await show_mining(query.from_user, query.message, True)


@dp.callback_query(F.data == "mine_start")
async def mine_start_callback(query: CallbackQuery) -> None:
    await query.answer("Mining started")
    await start_mining(query.from_user, query.message, True)


@dp.callback_query(F.data == "balance")
async def balance_callback(query: CallbackQuery) -> None:
    await query.answer()
    await show_balance(query.from_user, query.message, True)


@dp.callback_query(F.data == "referral")
async def referral_callback(query: CallbackQuery, bot: Bot) -> None:
    await query.answer()
    await show_referral(query.from_user, query.message, bot, True)


@dp.callback_query(F.data == "tasks")
async def tasks_callback(query: CallbackQuery) -> None:
    await query.answer()
    await show_tasks(query.from_user, query.message, True)


@dp.callback_query(F.data == "leaderboard")
async def leaderboard_callback(query: CallbackQuery) -> None:
    await query.answer()
    await show_leaderboard(query.from_user, query.message, True)


@dp.callback_query(F.data == "wallet")
async def wallet_callback(query: CallbackQuery) -> None:
    await query.answer()
    await show_wallet(query.from_user, query.message, True)


@dp.callback_query(F.data == "help")
async def help_callback(query: CallbackQuery) -> None:
    await query.answer()
    await show_help(query.from_user, query.message, True)


@dp.callback_query(F.data == "claim")
async def claim_callback(query: CallbackQuery, bot: Bot) -> None:
    await query.answer()
    await do_claim(query.from_user, query.message, bot, True)


async def main() -> None:
    await db.init()
    bot = Bot(token=settings.bot_token)

    await bot.set_my_commands([
        BotCommand(command="start", description="Open mining dashboard"),
        BotCommand(command="menu", description="Open main menu"),
        BotCommand(command="mine", description="Open mining center"),
        BotCommand(command="balance", description="View account balance"),
        BotCommand(command="referral", description="Invite friends"),
        BotCommand(command="leaderboard", description="View top miners"),
        BotCommand(command="help", description="How the bot works"),
    ])

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
