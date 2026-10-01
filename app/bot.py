from __future__ import annotations

import asyncio
import math
import time

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

from .config import get_settings
from .db import Database

settings = get_settings()
db = Database(settings.db_path)
dp = Dispatcher()


def mining_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛏ Start / Check Mining", callback_data="mine")],
        [InlineKeyboardButton(text="💰 Balance", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Referral", callback_data="referral")],
        [InlineKeyboardButton(text="🎁 Claim", callback_data="claim")],
    ])


def format_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


async def ensure_current_user(message: Message) -> None:
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)


@dp.message(CommandStart())
async def start_handler(message: Message, bot: Bot) -> None:
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

    bot_info = await bot.get_me()
    intro = (
        f"⛏ <b>Welcome to TG Mining Bot</b>\n\n"
        f"Mine internal MIN reward points in timed sessions.\n"
        f"Rate: <b>{settings.mining_rate_per_hour:g} MIN/hour</b>\n"
        f"Session: <b>{settings.mining_session_hours} hours</b>\n\n"
        f"Press the button below to start your first mining session."
    )
    if created and referrer_id:
        intro += "\n\n👥 Your referral has been recorded."

    await message.answer(intro, parse_mode="HTML", reply_markup=mining_keyboard())


@dp.message(Command("mine"))
async def mine_command(message: Message) -> None:
    await ensure_current_user(message)
    await send_mining_status(message)


async def send_mining_status(message: Message) -> None:
    user = await db.get_user(message.from_user.id)
    now = int(time.time())
    duration_seconds = settings.mining_session_hours * 3600

    if user and user.mining_ends_at is not None:
        if now >= user.mining_ends_at:
            text = "✅ Your mining session is complete. Press <b>Claim</b> to collect your MIN."
        else:
            remaining = user.mining_ends_at - now
            text = (
                "⛏ <b>Mining is active</b>\n\n"
                f"Rate: {settings.mining_rate_per_hour:g} MIN/hour\n"
                f"Time remaining: <b>{format_seconds(remaining)}</b>"
            )
        await message.answer(text, parse_mode="HTML", reply_markup=mining_keyboard())
        return

    started, ends_at = await db.start_mining(message.from_user.id, duration_seconds)
    if started:
        estimated = settings.mining_rate_per_hour * settings.mining_session_hours
        await message.answer(
            "⛏ <b>Mining started!</b>\n\n"
            f"Session: {settings.mining_session_hours} hours\n"
            f"Rate: {settings.mining_rate_per_hour:g} MIN/hour\n"
            f"Expected reward: <b>{estimated:g} MIN</b>\n\n"
            "You can close Telegram. The server tracks the session from timestamps.",
            parse_mode="HTML",
            reply_markup=mining_keyboard(),
        )


@dp.message(Command("claim"))
async def claim_command(message: Message, bot: Bot) -> None:
    await ensure_current_user(message)
    await process_claim(message, bot)


async def process_claim(message: Message, bot: Bot) -> None:
    status, value, rewarded_referrer = await db.claim_mining(
        telegram_id=message.from_user.id,
        rate_per_hour=settings.mining_rate_per_hour,
        referral_reward=settings.referral_reward,
    )

    if status == "not_started":
        await message.answer("You have no mining session to claim yet.", reply_markup=mining_keyboard())
        return
    if status == "not_ready":
        await message.answer(
            f"⏳ Mining is still active. Time remaining: <b>{format_seconds(int(value))}</b>",
            parse_mode="HTML",
            reply_markup=mining_keyboard(),
        )
        return
    if status == "missing":
        await message.answer("Run /start first.")
        return

    user = await db.get_user(message.from_user.id)
    await message.answer(
        f"🎉 <b>Claim successful</b>\n\n"
        f"Mined: <b>{value:g} MIN</b>\n"
        f"Balance: <b>{user.balance:g} MIN</b>\n\n"
        "Press Start Mining to begin another session.",
        parse_mode="HTML",
        reply_markup=mining_keyboard(),
    )

    if rewarded_referrer is not None:
        try:
            await bot.send_message(
                rewarded_referrer,
                f"👥 Your referral completed their first mining session.\n"
                f"Reward: <b>+{settings.referral_reward:g} MIN</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass


@dp.message(Command("balance"))
async def balance_command(message: Message) -> None:
    await ensure_current_user(message)
    await send_balance(message)


async def send_balance(message: Message) -> None:
    user = await db.get_user(message.from_user.id)
    total_refs = await db.referral_count(message.from_user.id)
    qualified = await db.qualified_referral_count(message.from_user.id)
    await message.answer(
        "💰 <b>Your account</b>\n\n"
        f"Balance: <b>{user.balance:g} MIN</b>\n"
        f"Referrals: <b>{total_refs}</b>\n"
        f"Qualified referrals: <b>{qualified}</b>",
        parse_mode="HTML",
        reply_markup=mining_keyboard(),
    )


@dp.message(Command("referral"))
async def referral_command(message: Message, bot: Bot) -> None:
    await ensure_current_user(message)
    await send_referral(message, bot)


async def send_referral(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    total = await db.referral_count(message.from_user.id)
    qualified = await db.qualified_referral_count(message.from_user.id)
    await message.answer(
        "👥 <b>Your referral link</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"Reward: <b>{settings.referral_reward:g} MIN</b> when a referral completes their first mining session.\n"
        f"Invited: {total} | Qualified: {qualified}",
        parse_mode="HTML",
        reply_markup=mining_keyboard(),
    )


@dp.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "<b>Commands</b>\n"
        "/start - open account\n"
        "/mine - start/check mining\n"
        "/claim - claim completed mining\n"
        "/balance - account balance\n"
        "/referral - personal referral link\n"
        "/help - show this message\n\n"
        "MIN is currently an internal reward point. This bot does not perform device proof-of-work mining.",
        parse_mode="HTML",
        reply_markup=mining_keyboard(),
    )


@dp.callback_query(F.data == "mine")
async def mine_callback(query: CallbackQuery) -> None:
    await query.answer()
    await send_mining_status(query.message)


@dp.callback_query(F.data == "balance")
async def balance_callback(query: CallbackQuery) -> None:
    await query.answer()
    await send_balance(query.message)


@dp.callback_query(F.data == "referral")
async def referral_callback(query: CallbackQuery, bot: Bot) -> None:
    await query.answer()
    await send_referral(query.message, bot)


@dp.callback_query(F.data == "claim")
async def claim_callback(query: CallbackQuery, bot: Bot) -> None:
    await query.answer()
    await process_claim(query.message, bot)


async def main() -> None:
    await db.init()
    bot = Bot(token=settings.bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
