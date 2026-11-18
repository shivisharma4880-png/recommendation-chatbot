from __future__ import annotations

import argparse
import asyncio
import logging
import html
import os
import re
from typing import List, Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from src.chips import category_children
from src.engine import RecommendationEngine, TurnResult
from src.filters import ShopperSlots
from src.session import SessionStore
from src.telegram_ui import (
    category_keyboard,
    followup_keyboard,
    format_preferences,
    format_turn,
    subcategory_keyboard,
    welcome_text,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
# httpx logs every request URL at INFO, and Telegram API URLs contain the bot token
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

sessions = SessionStore()
engine = RecommendationEngine()
BOT_USER_NAME = os.getenv("BOT_USER_NAME", "Shivi")


TELEGRAM_LIMIT = 4000


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> List[str]:
    """Split on paragraph/line boundaries so an HTML tag or entity is never cut in half."""
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    current = ""
    for block in re.split(r"(\n\n)", text):
        if len(current) + len(block) <= limit:
            current += block
            continue
        if current.strip():
            chunks.append(current.strip())
        current = ""
        while len(block) > limit:  # a single oversize block: cut at a line or space, never mid-tag
            cut = max(block.rfind("\n", 0, limit), block.rfind(" ", 0, limit))
            cut = cut if cut > 0 else limit
            if block.rfind("<", 0, cut) > block.rfind(">", 0, cut):
                cut = block.rfind("<", 0, cut) or cut
            chunks.append(block[:cut].strip())
            block = block[cut:]
        current = block
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]


async def _reply(message, text: str, markup) -> None:
    try:
        await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    except BadRequest:
        # malformed HTML must never swallow the answer: resend as plain text
        logger.warning("Telegram rejected HTML message; resending as plain text")
        plain = html.unescape(re.sub(r"<[^>]+>", "", text))
        await message.reply_text(plain[:TELEGRAM_LIMIT], reply_markup=markup)


async def _send_html(update: Update, text: str, markup=None) -> None:
    message = None
    if update.callback_query and update.callback_query.message:
        message = update.callback_query.message
    elif update.message:
        message = update.message
    if message is None:
        return
    chunks = split_message(text)
    for index, chunk in enumerate(chunks):
        await _reply(message, chunk, markup if index == len(chunks) - 1 else None)


async def _run_turn(chat_id: str, text: str, slots: ShopperSlots) -> TurnResult:
    return await asyncio.to_thread(engine.handle_turn, chat_id, text, slots)


async def _respond(update: Update, chat_id: str, text: str) -> None:
    slots = sessions.get(chat_id)
    try:
        result = await _run_turn(chat_id, text, slots)
    except Exception:
        logger.exception("Engine error for chat %s", chat_id)
        await _send_html(update, "Something went wrong. Please try again in a moment.")
        return
    sessions.update(chat_id, slots)
    await _send_html(update, format_turn(result), followup_keyboard(result.follow_ups))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat_id = str(update.effective_chat.id if update.effective_chat else update.message.chat_id)
    sessions.reset(chat_id)
    await update.message.reply_text(
        welcome_text(BOT_USER_NAME),
        parse_mode="HTML",
        reply_markup=category_keyboard(),
    )


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat_id = str(update.effective_chat.id if update.effective_chat else update.message.chat_id)
    sessions.reset(chat_id)
    await update.message.reply_text(
        "Preferences cleared. Pick a category to start again.",
        reply_markup=category_keyboard(),
    )


async def prefs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat_id = str(update.effective_chat.id if update.effective_chat else update.message.chat_id)
    slots = sessions.get(chat_id)
    await update.message.reply_text(format_preferences(slots), parse_mode="HTML")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            welcome_text(BOT_USER_NAME),
            parse_mode="HTML",
            reply_markup=category_keyboard(),
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    chat_id = str(update.effective_chat.id if update.effective_chat else update.message.chat_id)
    await _respond(update, chat_id, update.message.text.strip())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    chat_id = str(query.message.chat_id if query.message else query.from_user.id)
    data = query.data

    if data == "nav:home":
        await _send_html(update, "Pick a category:", category_keyboard())
        return

    if data.startswith("cat:"):
        title = data.split(":", 1)[1]
        markup = subcategory_keyboard(title)
        if markup:
            await _send_html(update, f"<b>{html.escape(title)}</b>\nChoose a type:", markup)
        return

    if data.startswith("sub:"):
        try:
            _, title, index_s = data.split(":", 2)
        except ValueError:
            return
        children = category_children(title)
        try:
            child = children[int(index_s)]
        except (ValueError, IndexError):
            await _send_html(update, "That option expired. Pick a category:", category_keyboard())
            return
        await _respond(update, chat_id, child["text"])
        return

    if data.startswith("fu:"):
        slots = sessions.get(chat_id)
        try:
            index = int(data.split(":", 1)[1])
            item = slots.last_follow_ups[index]
            text = item["text"]
        except (ValueError, IndexError, KeyError):
            await _send_html(update, "That option expired. Type your answer, or send /start.")
            return
        await _respond(update, chat_id, text)
        return


def check_ready() -> int:
    print(f"Catalogue: {len(engine.products)} products")
    print(f"LLM: {'ready (' + engine.grok.provider + ' / ' + engine.grok.model + ')' if engine.grok.available else 'missing GROQ_API_KEY'}")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    print(f"Telegram: {'token present' if token else 'missing TELEGRAM_BOT_TOKEN'}")
    if token and engine.grok.available:
        print("MVP is ready. Run: python -m src.telegram_bot")
        return 0
    print("Copy .env.example to .env and add the missing keys.")
    return 1


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Shivi's Product Assistant Telegram bot")
    parser.add_argument("--check", action="store_true", help="Verify catalogue, LLM, and Telegram token")
    args = parser.parse_args(argv)
    if args.check:
        raise SystemExit(check_ready())

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (from BotFather). Run with --check to see setup status.")
    if not engine.grok.available:
        logger.warning("GROQ_API_KEY is not set — intent extraction will use rules only.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("prefs", prefs_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Telegram bot polling as %s's Product Assistant Bot", BOT_USER_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
