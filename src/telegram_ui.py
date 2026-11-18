from __future__ import annotations

import html
from typing import Iterable, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.chips import CATEGORIES, category_children
from src.engine import TurnResult
from src.filters import ShopperSlots


def _rows(buttons: list[InlineKeyboardButton], per_row: int = 2) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def _label(item: dict) -> str:
    emoji = str(item.get("emoji") or "").strip()
    title = str(item.get("title") or "")
    return f"{emoji} {title}".strip() if emoji else title


def category_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(_label(item), callback_data=f"cat:{item['title']}")
        for item in CATEGORIES
    ]
    return InlineKeyboardMarkup(_rows(buttons, 1))


def subcategory_keyboard(title: str) -> Optional[InlineKeyboardMarkup]:
    children = category_children(title)
    if not children:
        return None
    buttons = [
        InlineKeyboardButton(_label(child), callback_data=f"sub:{title}:{index}")
        for index, child in enumerate(children)
    ]
    rows = _rows(buttons, 2)
    rows.append([InlineKeyboardButton("← Categories", callback_data="nav:home")])
    return InlineKeyboardMarkup(rows)


def followup_keyboard(follow_ups: Iterable[dict]) -> Optional[InlineKeyboardMarkup]:
    buttons = [
        InlineKeyboardButton(_label(item)[:32], callback_data=f"fu:{index}")
        for index, item in enumerate(follow_ups)
        if item.get("title")
    ]
    if not buttons:
        return None
    return InlineKeyboardMarkup(_rows(buttons, 2))


def format_products(products: list[dict]) -> str:
    blocks = []
    for product in products:
        name = html.escape(str(product.get("product_name") or ""))
        pid = html.escape(str(product.get("product_id") or ""))
        price = product.get("price_inr", "")
        sizes = html.escape(str(product.get("sizes") or ""))
        stock = html.escape(str(product.get("stock_status") or ""))
        colour = html.escape(str(product.get("colour") or ""))
        features = html.escape(str(product.get("key_features") or ""))
        emoji = html.escape(str(product.get("emoji") or "🛍️"))
        why = html.escape(str(product.get("why") or ""))
        why_line = f"\n{why}" if why else ""
        blocks.append(
            f"{emoji} <b>{name}</b> ({pid})\n"
            f"₹{price} · Sizes {sizes} · {stock}\n"
            f"<i>{colour} · {features}</i>{why_line}"
        )
    return "\n\n".join(blocks)


def format_comparison(comparison: dict) -> str:
    headers = [html.escape(str(h)) for h in (comparison.get("headers") or [])]
    rows = comparison.get("rows") or []
    if not headers or not rows:
        return ""
    lines = ["<b>Comparison</b>"]
    for row in rows:
        label = html.escape(str(row.get("label") or ""))
        values = row.get("values") or []
        parts = []
        for header, value in zip(headers, values):
            parts.append(f"{header}: {html.escape(str(value))}")
        lines.append(f"<b>{label}</b>\n" + "\n".join(parts))
    return "\n\n".join(lines)


def format_turn(result: TurnResult) -> str:
    reply = html.escape(result.reply)
    if result.handoff:
        reply = f"{reply}\n\n<i>Human handoff flagged. This demo cannot open a live agent chat.</i>"
    if result.comparison:
        table = format_comparison(result.comparison)
        if table:
            reply = f"{reply}\n\n{table}"
        return reply
    if not result.products:
        return reply
    return f"{reply}\n\n{format_products(result.products)}"


def format_preferences(slots: ShopperSlots) -> str:
    lines = slots.preference_lines()
    if not lines:
        return "No saved preferences yet. Send /start and pick a category, or tell me what you need."
    body = "\n".join(html.escape(line) for line in lines)
    return f"<b>Saved preferences</b>\n{body}"


def welcome_text(bot_name: str = "Shivi") -> str:
    return (
        f"<b>{html.escape(bot_name)}'s Product Assistant Bot</b>\n\n"
        "I recommend only products from our catalogue — no invented prices, stock, or delivery dates.\n\n"
        "Pick a category, or type the occasion, budget (INR), and size.\n\n"
        "/prefs — show saved preferences\n"
        "/reset — start over"
    )
