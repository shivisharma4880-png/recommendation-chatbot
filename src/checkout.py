"""In-memory checkout. Nothing is stored; PII lives only on the live shopper slots."""

from __future__ import annotations

import re
from typing import Optional

from src.catalogue import Product
from src.filters import CLOTHING_SIZES, ShopperSlots, parse_shoe_range, size_matches
from src.normalize import parse_sizes

SIZE_Q = "Which listed size should I use?"
NAME_Q = "What name should I put on this order?"
ADDRESS_Q = "Which city should I deliver to?"
PAYMENT_Q = "How would you like to pay?"
CONFIRM_Q = "Shall I place this order?"

QUESTION_BY_STEP = {
    "size": SIZE_Q,
    "name": NAME_Q,
    "address": ADDRESS_Q,
    "payment": PAYMENT_Q,
    "confirm": CONFIRM_Q,
}

QUESTION_MARKERS = (
    "which listed size should i use",
    "what name should i put on this order",
    "which city should i deliver to",
    "how would you like to pay",
    "shall i place this order",
)

CHECKOUT_DISK_FIELDS = (
    "checkout_step",
    "checkout_product_id",
    "checkout_size",
    "checkout_name",
    "checkout_address",
    "checkout_payment",
)

CANCEL_CHIP = {"title": "Cancel", "text": "Cancel checkout"}
CITY_CHIPS = [
    {"title": "Mumbai", "text": "Mumbai"},
    {"title": "Delhi", "text": "Delhi"},
    {"title": "Bengaluru", "text": "Bengaluru"},
    {"title": "Hyderabad", "text": "Hyderabad"},
]
PAYMENT_CHIPS = [
    {"title": "UPI", "emoji": "📱", "text": "UPI"},
    {"title": "Card", "emoji": "💳", "text": "Card"},
    {"title": "Cash on delivery", "emoji": "💵", "text": "COD"},
]
CONFIRM_CHIPS = [
    {"title": "Place order", "emoji": "✅", "text": "Place this order"},
    CANCEL_CHIP,
]

CANCEL_RE = re.compile(
    r"^\s*(cancel(?:\s+(?:the\s+|this\s+)?(?:checkout|order|purchase|buy))?|never mind|stop checkout|not now)\s*$",
    re.I,
)
PAYMENT_UPI = re.compile(r"\b(upi|gpay|google pay|phonepe|phone pe|paytm)\b", re.I)
PAYMENT_COD = re.compile(r"\b(cod|cash on delivery|cash)\b", re.I)
PAYMENT_CARD = re.compile(r"\b(cards?|credit|debit|visa|mastercard)\b", re.I)
CONFIRM_RE = re.compile(
    r"\b(place this order|place(?: the)? order|confirm|go ahead|yes|yeah|yep|yup|sure|ok(?:ay)?)\b",
    re.I,
)
NO_RE = re.compile(r"\b(no|nope|nah|not now|skip|nahi|no thanks|cancel)\b", re.I)
NAME_STRIP = re.compile(r"^(?:my name is|name is|i am|i'm|this is)\s+", re.I)
ADDRESS_STRIP = re.compile(
    r"^(?:deliver(?:y)?(?: it)?(?: to)?|ship(?:ping)?(?: it)?(?: to)?|send(?: it)? to|address(?: is)?)\s+",
    re.I,
)
NAME_FILLER = re.compile(
    r"^(thanks?|thank you|thx|ok(?:ay)?|cool|great|nice|got it|please|yes|yeah|yep)$",
    re.I,
)


def is_checkout_question(question: Optional[str]) -> bool:
    q = (question or "").lower()
    return any(marker in q for marker in QUESTION_MARKERS)


def clear(slots: ShopperSlots) -> None:
    slots.checkout_step = None
    slots.checkout_product_id = None
    slots.checkout_size = None
    slots.checkout_name = None
    slots.checkout_address = None
    slots.checkout_payment = None


def is_cancel(message: str) -> bool:
    return bool(CANCEL_RE.match((message or "").strip()))


def is_one_size(product: Product) -> bool:
    lower = product.sizes_raw.lower()
    return any(marker in lower for marker in ("one size", "free size", "adjustable"))


def listed_size_options(product: Product) -> list[str]:
    if is_one_size(product):
        return []
    if product.category == "Footwear":
        sizes: list[str] = []
        for lo, hi in parse_shoe_range(product.sizes_raw):
            for n in range(int(lo), int(hi) + 1):
                token = f"UK {n}"
                if token not in sizes:
                    sizes.append(token)
        return sizes
    bangles = re.findall(r"\d+\.\d+", product.sizes_raw)
    if bangles:
        out: list[str] = []
        for number in bangles:
            if number not in out:
                out.append(number)
        return out
    tokens = [part.strip().upper() for part in re.split(r"[,;/]", product.sizes_raw) if part.strip()]
    return [token for token in tokens if token in CLOTHING_SIZES or token == "XXXL"]


def matching_listed_size(product: Product, shopper_size: Optional[str]) -> Optional[str]:
    options = listed_size_options(product)
    if not options:
        return None
    for token in parse_sizes(shopper_size):
        if token in options:
            return token
        if size_matches(product, token) and token in options:
            return token
    return None


def needs_size(product: Product, slots: ShopperSlots) -> bool:
    if is_one_size(product) or not listed_size_options(product):
        return False
    return matching_listed_size(product, slots.size) is None


def start(slots: ShopperSlots, product: Product) -> None:
    ask_size = needs_size(product, slots)
    known_size = None
    if is_one_size(product):
        known_size = product.sizes_raw
    else:
        known_size = matching_listed_size(product, slots.size)
    clear(slots)
    slots.intent = "buy"
    slots.checkout_product_id = product.product_id
    slots.checkout_size = known_size
    slots.checkout_step = "size" if ask_size else "name"


def intro(product: Product) -> str:
    return (
        f"Let's check out {product.product_name} ({product.product_id}) — "
        f"₹{product.price_inr}, listed sizes {product.sizes_raw}, {product.stock_status}."
    )


def question_for(step: Optional[str]) -> str:
    return QUESTION_BY_STEP.get(step or "", NAME_Q)


def summary(product: Product, slots: ShopperSlots) -> str:
    return (
        f"Order for {product.product_name} ({product.product_id}) — ₹{product.price_inr}, "
        f"size {slots.checkout_size}, for {slots.checkout_name}, "
        f"delivery to {slots.checkout_address}, pay by {slots.checkout_payment}."
    )


def ask_text(product: Product, slots: ShopperSlots, *, include_intro: bool = False, retry: Optional[str] = None) -> str:
    parts: list[str] = []
    if include_intro:
        parts.append(intro(product))
    if retry:
        parts.append(retry)
    if slots.checkout_step == "confirm":
        parts.append(summary(product, slots))
    parts.append(question_for(slots.checkout_step))
    return "\n\n".join(parts)


def done_text(product: Product) -> str:
    return (
        f"Order confirmed for {product.product_name} ({product.product_id}). "
        f"Reference ORD-{product.product_id}. You can keep browsing the catalogue."
    )


def confirmation_payload(product: Product, slots: ShopperSlots, extra: Optional[dict] = None) -> dict:
    visual = extra or {}
    return {
        "reference": f"ORD-{product.product_id}",
        "status": "confirmed",
        "product_id": product.product_id,
        "product_name": product.product_name,
        "price_inr": product.price_inr,
        "colour": product.colour,
        "size": slots.checkout_size or product.sizes_raw,
        "name": slots.checkout_name,
        "address": slots.checkout_address,
        "payment": slots.checkout_payment,
        "stock_status": product.stock_status,
        "image_url": visual.get("image_url") or product.image_url,
        "emoji": visual.get("emoji") or "🛍️",
    }


def cancel_text(product: Product) -> str:
    return (
        f"Checkout for {product.product_name} is cancelled. "
        "You can keep browsing or pick another item."
    )


def follow_ups(slots: ShopperSlots, product: Optional[Product]) -> list[dict]:
    step = slots.checkout_step
    if step == "size":
        chips = []
        for option in listed_size_options(product) if product else []:
            if option.startswith("UK"):
                chips.append({"title": option, "text": option})
            elif re.match(r"\d+\.\d+", option):
                chips.append({"title": option, "text": f"Bangle size {option}"})
            else:
                chips.append({"title": option, "text": f"Size {option}"})
        return chips + [CANCEL_CHIP]
    if step == "name":
        return [CANCEL_CHIP]
    if step == "address":
        return CITY_CHIPS + [CANCEL_CHIP]
    if step == "payment":
        return PAYMENT_CHIPS + [CANCEL_CHIP]
    if step == "confirm":
        return list(CONFIRM_CHIPS)
    return []


def parse_size_answer(message: str, product: Product) -> Optional[str]:
    options = listed_size_options(product)
    wanted = parse_sizes(message)
    for token in wanted:
        if token in options:
            return token
        if size_matches(product, token) and (not options or token in options):
            return token
    raw = re.sub(r"\s+", " ", (message or "").strip())
    for option in options:
        if option.lower() == raw.lower():
            return option
    return None


def parse_name(message: str) -> Optional[str]:
    text = NAME_STRIP.sub("", (message or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text or NAME_FILLER.match(text) or is_cancel(text):
        return None
    if parse_sizes(text) and len(text.split()) <= 2 and not re.search(r"[A-Za-z]{3,}", text):
        return None
    cleaned = re.sub(r"[^A-Za-z .'-]", "", text).strip()
    if cleaned != text or not (2 <= len(cleaned) <= 40) or not re.search(r"[A-Za-z]", cleaned):
        return None
    return cleaned


def parse_address(message: str) -> Optional[str]:
    text = ADDRESS_STRIP.sub("", (message or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" .,")
    if not text or is_cancel(text) or len(text) < 3 or len(text) > 80:
        return None
    if NAME_FILLER.match(text):
        return None
    return text


def parse_payment(message: str) -> Optional[str]:
    if PAYMENT_UPI.search(message or ""):
        return "UPI"
    if PAYMENT_COD.search(message or ""):
        return "Cash on delivery"
    if PAYMENT_CARD.search(message or ""):
        return "Card"
    return None


def is_confirm(message: str) -> bool:
    return bool(CONFIRM_RE.search(message or "")) and not (
        NO_RE.search(message or "") and not re.search(r"\b(place|confirm|go ahead)\b", message or "", re.I)
    )


def is_decline(message: str) -> bool:
    return bool(NO_RE.search(message or "")) and not is_confirm(message)
