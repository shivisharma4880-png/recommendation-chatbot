"""Rule-based NLU: typos/slang, intent, and sentiment. Works without an LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from src.normalize import (
    requested_product_type,
    normalize_activity,
    normalize_category_and_type,
    normalize_occasion,
    normalize_style,
)

SLANG = {
    "gimme": "give me",
    "wanna": "want to",
    "gonna": "going to",
    "gotta": "have to",
    "lemme": "let me",
    "kinda": "kind of",
    "idk": "i do not know",
    "idc": "i do not care",
    "plz": "please",
    "pls": "please",
    "thx": "thanks",
    "ty": "thanks",
    "u": "you",
    "ur": "your",
    "n": "and",
    "w/": "with",
    "formals": "office",
    "workwear": "office",
    "9to5": "office",
    "ethnics": "festive",
    "desi": "festive",
    "partywear": "party",
    "kicks": "sneakers",
    "trainers": "sports shoes",
    "jwellery": "jewellery",
    "jewellry": "jewellery",
    "jewlery": "jewellery",
    "jewelry": "jewellery",
    "necklce": "necklace",
    "chappals": "sandals",
    "chappal": "sandals",
    "ballerinas": "flats",
    "ballerina": "flats",
    "sneekers": "sneakers",
    "sneakerz": "sneakers",
    "shaadi": "wedding",
    "shadi": "wedding",
    "sangeet": "wedding",
    "pooja": "festive",
    "diwali": "festive",
    "navratri": "festive",
    "workout": "gym",
    "exercise": "gym",
}

VOCAB = {
    "dress",
    "dresses",
    "saree",
    "lehenga",
    "kurta",
    "clutch",
    "bangle",
    "sandal",
    "necklaces",
    "earring",
    "anarkali",
    "sharara",
    "jumpsuit",
    "dinner",
    "wedding",
    "cocktail",
    "office",
    "festive",
    "casual",
    "party",
    "brunch",
    "gym",
    "running",
    "sports",
    "necklace",
    "earrings",
    "bracelet",
    "bangles",
    "watch",
    "watches",
    "jewellery",
    "flats",
    "sandals",
    "sneakers",
    "footwear",
    "shoes",
    "budget",
    "delivery",
    "return",
    "compare",
    "browse",
}

COLOURS = (
    "peach",
    "pastel",
    "pink",
    "wine",
    "rust",
    "emerald",
    "mint",
    "lilac",
    "mauve",
    "sage",
    "charcoal",
    "indigo",
    "grey",
    "gray",
    "red",
    "yellow",
    "orange",
    "purple",
    "brown",
    "multicolour",
    "black",
    "white",
    "navy",
    "blue",
    "green",
    "maroon",
    "gold",
    "silver",
    "rose gold",
    "beige",
    "tan",
    "ivory",
    "lavender",
    "olive",
    "coral",
    "nude",
    "champagne",
)

FRUSTRATION = re.compile(
    r"\b(frustrat\w*|annoyed|annoying|useless|stupid|waste|worst|terrible|horrible|"
    r"not helping|no help|already told|still not|this is wrong|give up|fed up|ridiculous)\b",
    re.I,
)
CONFUSION = re.compile(
    r"\b(confused|confusing|don't get|do not get|don't understand|not sure what you mean|"
    r"huh\b|wait what|what do you mean|i'm lost|im lost)\b",
    re.I,
)
EXCITEMENT = re.compile(
    r"\b(love this|perfect|amazing|awesome|yay|excited|brilliant|fantastic)\b",
    re.I,
)
POSITIVE = re.compile(r"\b(thanks|thank you|great|nice|helpful|cool)\b", re.I)
NEGATIVE = re.compile(r"\b(disappointed|unhappy|sad|meh|not good|don't like|do not like)\b", re.I)
HANDOFF = re.compile(
    r"\b(human|real person|actual person|agent|representative|customer care|"
    r"customer service|talk to someone|speak to someone|connect me)\b",
    re.I,
)
COMPARE = re.compile(
    r"\b(compare|comparison|versus|\bvs\b|difference between|which is better|"
    r"which one is better|or the other)\b",
    re.I,
)
BUY = re.compile(
    r"\b(buy|purchase|checkout|check out|add to cart|add to bag|order this|"
    r"place order|i'll take|i will take|i want this one)\b",
    re.I,
)
BROWSE = re.compile(
    r"\b(browse|show me|what's available|what is available|any options|"
    r"just looking|just browsing|looking around)\b",
    re.I,
)
FAQ = re.compile(
    r"\b(delivery|return|exchange|in stock|size chart|care for|cancel|wash this)\b",
    re.I,
)


@dataclass
class NLUResult:
    original: str
    corrected: str
    intent: str = "shop"
    sentiment: str = "neutral"
    handoff: bool = False
    slots: dict = field(default_factory=dict)


def levenshtein(a: str, b: str) -> int:
    """Optimal-string-alignment distance (insert/delete/substitute/adjacent swap each cost 1)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    rows = [list(range(len(b) + 1))]
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            value = min(row[j - 1] + 1, rows[i - 1][j] + 1, rows[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                value = min(value, rows[i - 2][j - 2] + 1)
            row.append(value)
        rows.append(row)
    return rows[-1][-1]


def _fuzzy_token(token: str) -> str:
    """Correct an obvious typo of a VOCAB word.

    Deliberately conservative: same first letter, one edit for words up to 8 letters (two beyond),
    and never for digits/currency tokens - so "shades" stays "shades" and "match" stays "match".
    """
    if len(token) < 4 or token in VOCAB or not token.isalpha():
        return token
    limit = 1 if len(token) <= 8 else 2
    best = None
    best_dist = limit + 1
    for word in sorted(VOCAB):
        if word[0] != token[0]:
            continue
        dist = levenshtein(token, word)
        if dist < best_dist:
            best = word
            best_dist = dist
        elif dist == best_dist:
            best = None
    if best is not None and 0 < best_dist <= limit:
        return best
    return token


def normalize(message: str) -> str:
    text = message.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[“”\"'’]", "", text)
    text = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", text)  # 10,000 -> 10000
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # keep 2.6, drop sentence dots
    text = re.sub(r"[!?,;:]+", " ", text)
    parts = []
    for raw in text.split():
        word = SLANG.get(raw, raw)
        parts.extend(word.split())
    corrected = [_fuzzy_token(part) for part in parts]
    return re.sub(r"\s+", " ", " ".join(corrected)).strip()


def detect_sentiment(text: str) -> str:
    if FRUSTRATION.search(text):
        return "frustrated"
    if CONFUSION.search(text):
        return "confused"
    if EXCITEMENT.search(text):
        return "excited"
    if NEGATIVE.search(text):
        return "negative"
    if POSITIVE.search(text):
        return "positive"
    return "neutral"


def detect_intent(text: str) -> str:
    if HANDOFF.search(text):
        return "handoff"
    if COMPARE.search(text):
        return "compare"
    if BUY.search(text) and not re.search(r"\b(can i|do you have|from this catalogue)\b", text):
        return "buy"
    if FAQ.search(text) and not re.search(r"\b(show|need|suggest|recommend)\b", text):
        return "faq"
    if BROWSE.search(text):
        return "browse"
    return "shop"


_NECKLINE = re.compile(
    r"\b((?:boat|round|v|u|square|sweetheart|halter|high|collar|collared|off[- ]shoulder|scoop|keyhole|mandarin|deep|plunging|strapless)"
    r"[- ]?(?:neck|neckline))\b"
)
_RECIPIENT = re.compile(
    r"\b(?:for|to)\s+(?:my|our)\s+(mother|mom|mum|mummy|maa|mother in law|sister|wife|girlfriend|friend|daughter|aunt|aunty|"
    r"grandmother|grandma|niece|colleague|boss)(?:s)?\b"
)
_GIFT_CUE = re.compile(r"\b(birthday|gift|gifting|anniversary|present|surprise)\b")
_RECIPIENT_CANON = {"mom": "mother", "mum": "mother", "mummy": "mother", "maa": "mother", "aunty": "aunt", "grandma": "grandmother"}


def extract_slots(text: str) -> dict:
    updates: dict = {}
    occasion = normalize_occasion(text)
    if occasion:
        updates["occasion"] = occasion
    activity = normalize_activity(text)
    if activity:
        updates["activity"] = activity
    ptype = requested_product_type(text)
    if ptype:
        cat, ptype = normalize_category_and_type(None, ptype)
        updates["product_type"] = ptype
        if cat:
            updates["category"] = cat
    colour_text = re.sub(r"\b\w+\s+(?:skin|skintone|complexion|undertone)\b", " ", text)  # "dusky skin" is not a colour
    colour_text = colour_text.replace("rose gold", "rosegold")
    found = []
    for colour in COLOURS + ("rosegold",):
        for m in re.finditer(rf"\b{re.escape(colour)}\b", colour_text):
            found.append((m.start(), "rose gold" if colour == "rosegold" else colour))
    ordered = []
    for _, colour in sorted(found):
        if colour not in ordered:
            ordered.append(colour)
    if ordered:
        updates["colour"] = ", ".join(ordered)
    style = normalize_style(text)
    if style:
        updates["style"] = style
    m = _NECKLINE.search(text)
    if m:
        updates["neckline"] = m.group(1).replace("-", " ")
    if _GIFT_CUE.search(text):
        m = _RECIPIENT.search(text)
        if m:
            who = m.group(1)
            updates["recipient"] = _RECIPIENT_CANON.get(who, who)
    return updates


def understand(message: str) -> NLUResult:
    corrected = normalize(message)
    blended = f"{message.lower()} {corrected}"
    intent = detect_intent(blended)
    if intent == "shop":
        intent = detect_intent(corrected)
    return NLUResult(
        original=message,
        corrected=corrected,
        intent=intent,
        sentiment=detect_sentiment(blended),
        handoff=bool(HANDOFF.search(blended)),
        slots=extract_slots(corrected),
    )
