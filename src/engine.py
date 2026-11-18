from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from src import checkout
from src import guards
from src.catalogue import FAQ, Product, get_catalogue
from src.faq_match import match_faq
from src.filters import (
    ShopperSlots,
    accessory_products,
    diagnose_no_match,
    explain_match,
    filter_products,
    rank_products,
    size_matches,
)
from src.grok_client import GrokClient
from src.nlu import understand
from src.normalize import (
    CLOTHING_TYPES,
    canonical_category,
    canonical_product_type,
    category_for_type,
    clean_text,
    normalize_activity,
    normalize_category_and_type,
    normalize_colour,
    normalize_occasion,
    normalize_size,
    normalize_style,
    parse_sizes,
    requested_product_type,
    size_kind,
)
from src.chips import category_children
from src.visuals import visual_for

load_dotenv()
logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 1000

RUNNING_AND_GYM = re.compile(r"running.*gym|gym.*running", re.I)
ACCESSORY_TYPES = {
    "jewellery",
    "necklace",
    "earrings",
    "bracelet",
    "bangles",
    "watch",
    "bag",
    "clutch",
}
ACCESSORY_QUESTION = "Would you like matching jewellery or a clutch from the catalogue?"
COMPARE_QUESTION = "Which catalogue products should I compare?"
COMPARE_MORE_QUESTION = "Name or pick one more catalogue product to compare."
NECKLINE_QUESTION = (
    "What is the neckline of your outfit (for example boat, round, V or high collar)? Say skip if you are not sure."
)
GIFT_STYLE_QUESTION = "Would you say their style is traditional, minimal or statement?"
CHANGE_WORDS = re.compile(
    r"\b(change|changing|update|modify|edit|switch|different|another|instead|revise|reset|clear|remove)\b"
)


@dataclass
class TurnResult:
    reply: str
    products: list[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    follow_ups: list[dict] = field(default_factory=list)
    intent: str = "shop"
    sentiment: str = "neutral"
    handoff: bool = False
    comparison: Optional[dict] = None
    confirmation: Optional[dict] = None


BUDGET_FOLLOW_UPS = [
    {"title": "Under ₹1,000", "emoji": "🪙", "text": "My maximum budget is 1000 rupees"},
    {"title": "Under ₹2,000", "emoji": "🪙", "text": "My maximum budget is 2000 rupees"},
    {"title": "Under ₹3,000", "emoji": "🪙", "text": "My maximum budget is 3000 rupees"},
    {"title": "Under ₹5,000", "emoji": "🪙", "text": "My maximum budget is 5000 rupees"},
    {"title": "Under ₹10,000", "emoji": "🪙", "text": "My maximum budget is 10000 rupees"},
]
SIZE_FOLLOW_UPS = [
    {"title": "XS", "text": "Size XS"},
    {"title": "S", "text": "Size S"},
    {"title": "M", "text": "Size M"},
    {"title": "L", "text": "Size L"},
    {"title": "XL", "text": "Size XL"},
    {"title": "XXL", "text": "Size XXL"},
    {"title": "Size help", "emoji": "📏", "text": "How do I choose the right size?"},
]
SHOE_SIZE_FOLLOW_UPS = [
    {"title": "UK 4", "text": "UK 4"},
    {"title": "UK 5", "text": "UK 5"},
    {"title": "UK 6", "text": "UK 6"},
    {"title": "UK 7", "text": "UK 7"},
    {"title": "UK 8", "text": "UK 8"},
]
PRIORITY_FOLLOW_UPS = [
    {"title": "Running", "emoji": "🏃", "text": "Running is the priority"},
    {"title": "Gym", "emoji": "🏋️", "text": "Gym is the priority"},
]
INTAKE_FAQS = [
    {"title": "Delivery", "emoji": "📦", "text": "How long will delivery take?"},
    {"title": "In stock?", "emoji": "✅", "text": "Are these products in stock?"},
]
BANGLE_SIZE_FOLLOW_UPS = [
    {"title": "2.4", "text": "Bangle size 2.4"},
    {"title": "2.6", "text": "Bangle size 2.6"},
    {"title": "2.8", "text": "Bangle size 2.8"},
]
NECKLINE_FOLLOW_UPS = [
    {"title": "Boat neck", "text": "It has a boat neckline"},
    {"title": "Round neck", "text": "It has a round neckline"},
    {"title": "V-neck", "text": "It has a V neckline"},
    {"title": "High / collar", "text": "It has a high collar neckline"},
    {"title": "Skip", "text": "Skip the neckline"},
]
GIFT_STYLE_FOLLOW_UPS = [
    {"title": "Traditional", "emoji": "🪔", "text": "Traditional style"},
    {"title": "Minimal", "emoji": "◻️", "text": "Minimal style"},
    {"title": "Statement", "emoji": "✨", "text": "Statement style"},
]
FOOTWEAR_REFINE_FOLLOW_UPS = [
    {"title": "Checkout", "emoji": "🛍️", "text": "Checkout this item"},
    {"title": "Cheaper", "emoji": "💸", "text": "Show me cheaper options"},
    {"title": "Compare", "emoji": "⚖️", "text": "I want to compare products"},
    {"title": "Another colour", "emoji": "🎨", "text": "I want to change the colour"},
    {"title": "Different size", "emoji": "📏", "text": "I want to change my size"},
]
ACCESSORY_FOLLOW_UPS = [
    {"title": "Yes, accessories", "emoji": "💎", "text": "Yes, please suggest jewellery or a clutch"},
    {"title": "No thanks", "text": "No, skip accessories"},
]
REFINE_FOLLOW_UPS = [
    {"title": "Checkout", "emoji": "🛍️", "text": "Checkout this item"},
    {"title": "Cheaper", "emoji": "💸", "text": "Show me cheaper options"},
    {"title": "Compare", "emoji": "⚖️", "text": "I want to compare products"},
    {"title": "Minimal", "emoji": "◻️", "text": "I prefer a minimal style"},
    {"title": "Traditional", "emoji": "🪔", "text": "I prefer a traditional style"},
    {"title": "Another colour", "emoji": "🎨", "text": "I want to change the colour"},
]
CHEAPER = re.compile(r"\b(cheaper|less expensive|lower budget|more affordable)\b", re.I)
SIMILAR = re.compile(r"\b(similar|like that|like the first|more like)\b", re.I)
GO_BACK = re.compile(r"^(?:←\s*)?(?:go back|back)$", re.I)
BACK_CHIP = {"title": "Back", "emoji": "←", "text": "Go back"}
TYPE_QUESTION = "Which type would you like?"
MAIN_MENU_QUESTION = "Would you like occasions, accessories, or footwear?"
MAIN_MENU_FOLLOW_UPS = [
    {"title": "Occasions", "emoji": "✨", "text": "I want to browse outfits by occasion"},
    {"title": "Accessories", "emoji": "💎", "text": "Show me jewellery and accessories"},
    {"title": "Footwear", "emoji": "👟", "text": "Show me footwear from the catalogue"},
]
CHANGE_FOLLOW_UPS = [
    {"title": "Budget", "emoji": "🪙", "text": "I want to change my budget"},
    {"title": "Size", "emoji": "📏", "text": "I want to change my size"},
    {"title": "Occasion", "emoji": "✨", "text": "I want to change the occasion"},
    {"title": "Colour", "emoji": "🎨", "text": "I want to change the colour"},
]
CHANGE_REQUIREMENT_QUESTION = (
    "Would you like to change one requirement (budget, size, colour, or occasion)?"
)
HANDOFF_FOLLOW_UPS = [
    {"title": "Keep shopping", "emoji": "🛍️", "text": "I still want catalogue help"},
    {"title": "Talk to a person", "emoji": "👤", "text": "Please connect me to a human"},
]
HANDOFF_REPLY = (
    "I'll pause the product search and flag this for a human teammate. "
    "This demo cannot open a live agent chat from here, but you can keep using the catalogue assistant if you prefer."
)
SPECIFIC_INTENTS = {
    "browse",
    "compare",
    "buy",
    "faq",
    "change_requirement",
    "accessories_yes",
    "accessories_no",
    "handoff",
}
THIS_ONE = re.compile(
    r"\b(this one|that one|the first|i['’]?ll take it|i will take it|buy it|purchase it|"
    r"checkout this|check out this)\b",
    re.I,
)
COMPARE_THESE = re.compile(
    r"\b(these|them|those|the (?:two|three|items?|products?|ones)|this shortlist|the shortlist)\b",
    re.I,
)
COMPARE_FIELDS = [
    ("product_id", "ID"),
    ("product_type", "Type"),
    ("price_inr", "Price"),
    ("colour", "Colour"),
    ("material", "Material"),
    ("sizes_raw", "Sizes"),
    ("occasions", "Occasions"),
    ("stock_status", "Stock"),
    ("key_features", "Features"),
    ("style_tags", "Style"),
    ("care_instructions", "Care"),
]


REFINE_RESET_WORDS = re.compile(r"\b(skip|no colou?r|no preference|any colou?r)\b")
UNSUPPORTED = re.compile(
    r"\b(perfumes?|fragrances?|deodorants?|makeup|make-up|lipsticks?|cosmetics?|skincare|laptops?|phones?|mobiles?|"
    r"tvs?|televisions?|electronics?|furniture|grocer\w+|books?|toys?|kids?|child\w*|babys?|boys?|mens?|men|gents|"
    r"menswear|jeans|denim|jackets?|coats?|sweaters?|hoodies?|skirts?|shorts|boots?|sunglasses|belts?|wallets?|"
    r"scarf|scarves|stoles?|hats?|socks|lingerie|swimsuits?|bikinis?|nightwear|pyjamas?|rings?|anklets?|"
    r"hair ?(?:clips?|bands?)|maangtikka|nose ?pins?)\b"
)
MEN_WORDS = {"men", "mens", "gents", "menswear", "boy", "boys"}
GREETING = re.compile(r"^\s*(hi+|hello+|hey+|hola|namaste|good (morning|afternoon|evening))\W*$", re.I)
THANKS = re.compile(r"^\s*(thanks?|thank you|thx|ok(ay)?|cool|great|nice|got it)\W*$", re.I)
YES_WORDS = re.compile(r"\b(yes|yeah|yep|yup|sure|ok(ay)?|please|haan|ha|definitely|go ahead|why not)\b")
NO_WORDS = re.compile(r"\b(no|nope|nah|not now|skip|nahi|no thanks|maybe later|don'?t)\b")
SHOP_VERBS = re.compile(r"\b(show|suggest|recommend|find|looking|need|want|give me|dikhao|chahiye)\b")
OWNED_OUTFIT_NOUN = r"(?:dress|outfit|saree|sari|kurta|kurti|lehenga|gown|suit|anarkali|top|shirt|co-?ord|jumpsuit)"
ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "last": -1}
ATTRIBUTE_PATTERNS = [
    ("price", re.compile(r"\b(price|prices|cost|costs|how much|kitn[ae]|daam|rate|rs|rupees?)\b|₹")),
    ("material", re.compile(r"\b(material|fabric|made (?:of|from|out of)|kapda)\b")),
    ("care", re.compile(r"\b(care|wash|washing|clean|cleaning|dry ?clean|laundry)\b")),
    ("sizes", re.compile(r"\b(sizes?|available in|come in|comes in)\b")),
    ("stock", re.compile(r"\b(stock|availab\w+|left)\b")),
    ("colour", re.compile(r"\b(colou?rs?)\b")),
    ("occasion", re.compile(r"\b(occasions?|suitable for|good for|used for|wear it)\b")),
    ("features", re.compile(r"\b(features?|details?|describe|tell me (?:more )?about|about (?:this|it)|info|information)\b")),
]
REFERENT = re.compile(r"\b(this|it|these|that|those|the first|second|third|last|ye|yeh|iska|isko|iski|is wale|first one|second one)\b")


def _plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


class RecommendationEngine:
    def __init__(
        self,
        catalogue_path: Optional[Path] = None,
        grok: Optional[GrokClient] = None,
    ):
        path = catalogue_path
        if path is None:
            env_path = os.getenv("CATALOGUE_PATH")
            if env_path:
                path = Path(env_path)
                if not path.is_absolute():
                    path = Path(__file__).resolve().parent.parent / path
        self.products, self.faqs, self.personas = get_catalogue(path)
        self.grok = grok or GrokClient()
        self.last_guard_failure: Optional[str] = None

    # ------------------------------------------------------------------ parsing helpers
    @staticmethod
    def _amount(number: str, suffix: Optional[str]) -> Optional[int]:
        try:
            value = float(number)
        except ValueError:
            return None
        mult = 1
        if suffix:
            suffix = suffix.lower()
            mult = 1000 if suffix in ("k", "thousand") else 100000
        amount = int(round(value * mult))
        return amount if 50 <= amount <= 100000 else None

    @staticmethod
    def _parse_budget(message: str, last_question: Optional[str]) -> Optional[int]:
        """Parse a maximum budget in INR from free text. Returns None when no budget is stated."""
        raw = message.lower().strip()
        awaiting_change = bool(last_question and "requirement" in last_question.lower())
        asking = bool(last_question and "budget" in last_question.lower()) or awaiting_change
        text = raw.replace(",", "").replace("₹", " ₹ ")
        num = r"(?<![\d.])(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lac)?(?![\d])(?!\.\d)"
        cur = r"(?:₹|rs\.?|inr|rupees?|rupay[ae]?)?\s*"
        patterns = [
            rf"between\s+{cur}\d+(?:\.\d+)?\s*(?:k)?\s*(?:and|to|-)\s*{cur}{num}",
            rf"\b(?:under|below|upto|up to|max(?:imum)?|within|less than|lesser than|not more than|at most|around|about|approx(?:imately)?|"
            rf"budget(?:\s+(?:is|of|:))?|limit(?:\s+is)?|price range(?:\s+is)?)\s*(?:of\s+)?{cur}{num}",
            rf"\b(?:change|update|make|set|increase|raise|reduce|lower|decrease|switch|increase|actually|now|new)\b[^\d₹]{{0,30}}?\b(?:to|at|=|it|be)?\s*{cur}{num}",
            rf"(?:₹|\brs\.?|\binr)\s*{num}",
            rf"{num}\s*(?:rupees?|rs\b|inr\b|rupay[ae]?\b|ke andar|ke ander|ke neeche|tak\b|se kam|ke bhitar)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                amount = RecommendationEngine._amount(m.group(1), m.group(2))
                if amount is not None:
                    return amount
        k_loose = re.search(r"(?<![\d.])(\d+)\s*k\b", text)
        asking_size = bool(last_question and "size" in last_question.lower()) and not awaiting_change
        if k_loose and not asking_size:
            return RecommendationEngine._amount(k_loose.group(1), "k")
        bare = re.fullmatch(r"\s*(\d+)\s*(k)?\s*", text)
        if bare:
            amount = RecommendationEngine._amount(bare.group(1), bare.group(2))
            if amount is not None and (amount >= (300 if awaiting_change else 500) or (asking and not awaiting_change)) and not asking_size:
                return amount
        return None

    @staticmethod
    def _llm_budget(value, message: str) -> Optional[int]:
        """Accept an LLM budget only when that number really appears in the shopper's message."""
        try:
            amount = int(float(value))
        except (TypeError, ValueError):
            return None
        if not 50 <= amount <= 100000:
            return None
        text = message.lower().replace(",", "")
        for m in re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lac)?(?![\d])(?!\.\d)", text):
            candidate = RecommendationEngine._amount(m.group(1), m.group(2))
            if candidate == amount:
                return amount
        return None

    @staticmethod
    def _parse_size(message: str, slots: ShopperSlots) -> Optional[str]:
        last_q = (slots.last_question_asked or "").lower()
        asking = "size" in last_q
        asking_uk = "uk shoe" in last_q
        lower = message.lower().strip()
        uk = re.search(r"\b(uk\s*\d+(?:\.\d+)?)\b", lower)
        if uk:
            return normalize_size(uk.group(1))
        bangle = re.search(r"(?<![\d.])(2\.\d)(?![\d.])", lower)
        if bangle and (asking or "bangle" in lower or "size" in lower):
            return bangle.group(1)
        labelled = re.search(
            r"\bsize\s*(?:is|to|of|=|:)?\s*(?:a\s+)?(xxxl|xxl|xxs|xs|xl|s|m|l|small|medium|large)\b"
            r"(?:\s*(?:or|and|/|,)\s*(xxxl|xxl|xxs|xs|xl|s|m|l|small|medium|large)\b)?",
            lower,
        )
        if labelled:
            return normalize_size(" ".join(g for g in labelled.groups() if g).upper())
        shoe_num = re.search(r"\bsize\s*(?:is|to|of|=|:)?\s*(\d{1,2}(?:\.5)?)\b", lower)
        if shoe_num and (asking_uk or slots.category == "Footwear"):
            n = float(shoe_num.group(1))
            if 2 <= n <= 13:
                return normalize_size(f"UK {shoe_num.group(1)}")
        if asking and len(lower.split()) <= 10:
            if asking_uk:
                n = re.fullmatch(r"\s*(\d{1,2}(?:\.5)?)\s*", lower)
                if n and 2 <= float(n.group(1)) <= 13:
                    return normalize_size(f"UK {n.group(1)}")
            sizes = parse_sizes(message)
            if sizes:
                return normalize_size(message)
        # a bare clothing size ("XL", "try L") while a clothing search is already running
        family = RecommendationEngine._family(slots.category, slots.product_type)
        if (slots.last_products or RecommendationEngine._has_active_request(slots)) and family in (None, "clothing"):
            bare = re.fullmatch(
                r"(?:(?:try|make it|in|for|show|change to|switch to|what about|how about|and|actually)\s+)*"
                r"(xxxl|xxl|xxs|xs|xl|s|m|l)(?:\s+(?:please|pls|size))?[.!]*",
                lower,
            )
            if bare and canonical_product_type(slots.product_type) != "bangles":
                return normalize_size(bare.group(1).upper())
        return None

    @staticmethod
    def _llm_size(value, message: str) -> Optional[str]:
        sizes = parse_sizes(value)
        if not sizes:
            return None
        in_message = set(parse_sizes(message))
        if all(s in in_message for s in sizes):
            return ", ".join(sizes)
        return None

    # ------------------------------------------------------------------ slot extraction
    def _llm_parse(self, message: str, slots: ShopperSlots) -> dict:
        if not self.grok.available:
            return {}
        try:
            parsed = self.grok.parse_message(message, slots.to_context_dict())
        except Exception as exc:  # network, JSON, quota... -> rules only
            logger.warning("LLM parse failed (%s); using rule-based parsing", type(exc).__name__)
            return {}
        return parsed if isinstance(parsed, dict) else {}

    STYLING_CUE = re.compile(
        r"\b(jewell?ery|earrings?|necklaces?|bangles?|bracelets?|accessor\w+)\b[^.?!]{0,40}?\b(go|goes|going|look|looks|match|matching|suit|suits|pair|complement|wear|worn)\b"
        r"[^.?!]{0,20}?\b(with|good|well)\b"
    )

    def _extract_updates(self, message: str, parse_text: str, nlu, parsed: dict, slots: ShopperSlots) -> dict:
        """Slot updates from this message: validated LLM values first, rule-based NLU fills the gaps."""
        u: dict = {}
        lower = message.lower()
        budget = self._parse_budget(parse_text, slots.last_question_asked)
        if budget is None:
            budget = self._llm_budget(parsed.get("budget_max"), message)
        if budget is not None:
            u["budget_max"] = budget
        size = self._parse_size(parse_text, slots)
        if not size:
            size = self._llm_size(parsed.get("size"), message)
        if size:
            u["size"] = size

        cat, ptype = normalize_category_and_type(parsed.get("category"), parsed.get("product_type"))
        n_cat, n_type = nlu.slots.get("category"), nlu.slots.get("product_type")
        if (cat or ptype) and not (n_cat or n_type):
            # the LLM must not invent a product type the shopper never wrote ("show me in black" -> kurta)
            word_hit = (ptype and re.search(rf"\b{re.escape(ptype.split()[0].rstrip('s'))}", lower)) or (
                cat and re.search(rf"\b{re.escape(cat.split()[0].lower().rstrip('s'))}", lower)
            )
            if not word_hit:
                cat, ptype = None, None
        if not cat and not ptype:
            cat, ptype = n_cat, n_type
        elif cat and not ptype and n_type and category_for_type(n_type) in (None, cat):
            ptype = n_type
        elif ptype and not cat:
            cat = category_for_type(ptype)
        if cat:
            u["category"] = cat
        if ptype:
            u["product_type"] = ptype

        occasion = normalize_occasion(parsed.get("occasion")) or nlu.slots.get("occasion")
        if occasion:
            u["occasion"] = occasion
        activity = normalize_activity(parsed.get("activity")) or nlu.slots.get("activity")
        if activity:
            u["activity"] = activity

        colour = normalize_colour(parsed.get("colour"))
        if colour:
            # keep only terms the shopper actually wrote ("peach or pastel shades" -> peach, pastel)
            kept = [t for t in colour.split(", ") if re.search(rf"\b{re.escape(t.split()[0])}", lower)]
            colour = ", ".join(kept) if kept else None
        colour = colour or nlu.slots.get("colour")
        if colour:
            u["colour"] = colour
        outfit_colour = normalize_colour(parsed.get("outfit_colour"))
        if outfit_colour:
            u["outfit_colour"] = outfit_colour
        style = normalize_style(parsed.get("style")) or nlu.slots.get("style")
        if style:
            u["style"] = style
        for key in ("metal", "look"):
            value = clean_text(parsed.get(key), 40)
            if value and re.search(re.escape(value.split()[0].lower()), lower):
                u[key] = value
        neckline = clean_text(parsed.get("neckline"), 30) or nlu.slots.get("neckline")
        if neckline:
            u["neckline"] = neckline.lower()
        recipient = nlu.slots.get("recipient")
        if not recipient and parsed.get("recipient") and re.search(r"\b(birthday|gift|anniversary|present)\b", lower):
            recipient = clean_text(parsed.get("recipient"), 24)
        if recipient:
            u["recipient"] = recipient.lower()
        outfit_word = re.search(r"\b(outfits?|clothes|clothing|apparel)\b", lower)
        other_family = re.search(r"\b(shoes?|sandals?|sneakers?|flats|footwear|jewell?ery|earrings?|necklaces?|bangles?|bracelets?|watch(?:es)?|bags?|clutch(?:es)?)\b", lower)
        answering_occasion = "outfit for" in (slots.last_question_asked or "").lower()
        new_cat = u.get("category")
        if not other_family and new_cat in (None, "Ethnic wear", "Western wear") and (
            outfit_word or (answering_occasion and (u.get("occasion") or u.get("activity")))
        ):
            u["scope"] = "clothing"
            if outfit_word and not u.get("category") and not u.get("product_type"):
                u["_clear_type"] = True
        priority = str(parsed.get("activity_priority") or "").lower()
        if re.search(r"\brunning\b", lower) and "priority" in lower:
            priority = "running"
        elif re.search(r"\bgym\b", lower) and "priority" in lower:
            priority = "gym"
        if priority in {"running", "gym"}:
            u["outfit_priority"] = priority
        # a colour attached to an outfit the shopper already owns is a styling hint, not a product filter
        if u.get("colour") and (u.get("category") or slots.category) in ("Jewellery", "Accessories", "Footwear"):
            cat_now = u.get("category") or slots.category
            owned = re.search(rf"\b({'|'.join(re.escape(c.split()[0]) for c in u['colour'].split(', '))})\b[- ]?(?:coloured|colored)?\s+(?:\w+\s+)?{OWNED_OUTFIT_NOUN}\b", lower)
            owned = owned or re.search(rf"\b(?:with|match(?:ing)?|goes with|go with|complement|pair)\b[^.?!]{{0,25}}\b{OWNED_OUTFIT_NOUN}\b", lower)
            owned = owned or (cat_now == "Jewellery" and self.STYLING_CUE.search(lower))
            if owned or (cat_now == "Jewellery" and u.get("outfit_colour")):
                u["outfit_colour"] = u["outfit_colour"] if u.get("outfit_colour") else u.pop("colour")
                u.pop("colour", None)
        return u

    @staticmethod
    def _family(category: Optional[str], product_type: Optional[str]) -> Optional[str]:
        if category in ("Ethnic wear", "Western wear"):
            return "clothing"
        if category == "Jewellery":
            return "jewellery"
        if category == "Accessories":
            return "accessories"
        if category == "Footwear":
            return "footwear"
        canon = canonical_product_type(product_type)
        if canon in CLOTHING_TYPES:
            return "clothing"
        return None

    def _apply_updates(self, slots: ShopperSlots, u: dict) -> None:
        """Merge updates; a new shopping goal (clothes -> jewellery -> shoes) drops fields that no longer apply."""
        clear_type = bool(u.pop("_clear_type", False))
        sporty = {"gym", "running", "sports", "training"}
        # a new occasion replaces a stale activity (and vice versa): the two are ANDed by the filters,
        # so keeping "gym" after "festive" makes every search empty
        if u.get("occasion") and u.get("activity") and set(re.findall(r"[a-z]+", u["occasion"])) <= sporty:
            u.pop("occasion")
        if u.get("occasion") and not u.get("activity") and not set(re.findall(r"[a-z]+", u["occasion"])) <= sporty:
            slots.activity = None
            slots.outfit_priority = None
        if u.get("activity") and not u.get("occasion"):
            slots.occasion = None
        old_family = self._family(slots.category, slots.product_type)
        new_family = self._family(u.get("category"), u.get("product_type")) if ("category" in u or "product_type" in u) else None
        if new_family and old_family and new_family != old_family:
            for key in ("size", "activity", "outfit_priority", "colour", "style", "neckline"):
                if key not in u:
                    setattr(slots, key, None)
            slots.category = None
            slots.product_type = None
            slots.last_products = []
            slots.scope = None
        elif "product_type" in u and u["product_type"] != slots.product_type:
            if "activity" not in u:
                slots.activity = None
            if "outfit_priority" not in u:
                slots.outfit_priority = None
            if "category" not in u:
                slots.category = category_for_type(u["product_type"])  # may be None (a plain "dress")
        if "category" in u and "product_type" not in u:
            ptype = canonical_product_type(slots.product_type)
            if ptype and category_for_type(ptype) not in (None, u["category"]):
                slots.product_type = None
        if clear_type and not u.get("category") and not u.get("product_type"):
            # "I need casual everyday outfits" after shoes/jewellery: a fresh clothing request
            slots.category = None
            slots.product_type = None
            slots.last_products = []
        slots.merge(u)
        if new_family and new_family != "clothing":
            slots.scope = None
        # a size of the wrong kind (UK 6 for clothes, M for shoes) cannot apply to the current search
        want = {"clothing": "clothing", "footwear": "shoe"}.get(self._family(slots.category, slots.product_type) or (slots.scope == "clothing" and "clothing" or ""))
        if canonical_product_type(slots.product_type) == "bangles":
            want = "bangle"
        if want and slots.size and "size" not in u:
            kinds = {size_kind(x) for x in parse_sizes(slots.size)}
            if kinds and kinds != {want}:
                slots.size = None
        if slots.activity and slots.outfit_priority and not RUNNING_AND_GYM.search(slots.activity):
            slots.outfit_priority = None  # priority only makes sense when both running and gym were named

    @staticmethod
    def _answer_is_colour_skip(parse_text: str, slots: ShopperSlots) -> bool:
        last_q = (slots.last_question_asked or "").lower()
        return "colour should i filter" in last_q and bool(REFINE_RESET_WORDS.search(parse_text))

    def _detect_change_field(self, parse_text: str, slots: ShopperSlots, parsed: dict) -> str:
        last = (slots.last_question_asked or "").lower()
        awaiting = "requirement" in last
        changing = awaiting or bool(CHANGE_WORDS.search(parse_text))
        if not changing:
            return ""
        if re.search(r"\b(budget|budgets|price)\b", parse_text):
            return "budget"
        if re.search(r"\bsizes?\b", parse_text):
            return "size"
        if re.search(r"\b(colou?r|colours|colors)\b", parse_text):
            return "colour"
        if re.search(r"\boccasions?\b", parse_text):
            return "occasion"
        return ""

    def _apply_requirement_change(self, field_name: str, u: dict, slots: ShopperSlots) -> bool:
        """Clear a slot the shopper wants to change, unless the same message already supplies the new value."""
        if not field_name:
            return False
        key_map = {"budget": "budget_max", "size": "size", "colour": "colour", "occasion": "occasion"}
        if key_map[field_name] in u:
            return False  # "change budget to 9000": already updated
        if field_name == "budget":
            slots.budget_max = None
        elif field_name == "size":
            slots.size = None
        elif field_name == "colour":
            slots.colour = None
        elif field_name == "occasion":
            slots.occasion = None
            slots.activity = None
        return True

    # ------------------------------------------------------------------ follow-up chips
    @staticmethod
    def _with_back(items: list[dict]) -> list[dict]:
        chips = list(items or [])
        if any(str(item.get("text") or "").strip().lower() == "go back" for item in chips):
            return chips
        return [BACK_CHIP] + chips

    def _type_menu_follow_ups(self, slots: ShopperSlots) -> list[dict]:
        if slots.category in ("Jewellery", "Accessories"):
            return category_children("Accessories")
        if slots.category == "Footwear":
            return category_children("Footwear")
        return category_children("Occasions")

    def _go_back(self, slots: ShopperSlots) -> TurnResult:
        slots.awaiting_compare = False
        slots.compare_ids = []
        slots.last_products = []
        slots.offered_accessories = False
        if slots.product_type:
            slots.product_type = None
            slots.last_question_asked = TYPE_QUESTION
            return self._reply(
                slots,
                "Back to types. Pick another option below, or go back again for the main menu.",
                question=TYPE_QUESTION,
            )
        slots.category = None
        slots.scope = None
        slots.last_question_asked = MAIN_MENU_QUESTION
        return self._reply(
            slots,
            "Back to the main menu. Choose occasions, accessories, or footwear.",
            question=MAIN_MENU_QUESTION,
        )

    def _follow_ups(self, slots: ShopperSlots, question: Optional[str] = None) -> list[dict]:
        question = question or slots.last_question_asked
        if slots.checkout_step:
            product = self._product_by_id(slots.checkout_product_id)
            return checkout.follow_ups(slots, product)
        if question:
            q = question.lower()
            if checkout.is_checkout_question(question):
                product = self._product_by_id(slots.checkout_product_id)
                return checkout.follow_ups(slots, product)
            if question == TYPE_QUESTION or "which type would you like" in q:
                return self._with_back(self._type_menu_follow_ups(slots))
            if question == MAIN_MENU_QUESTION or "occasions, accessories, or footwear" in q:
                return list(MAIN_MENU_FOLLOW_UPS)
            if "requirement" in q:
                return self._with_back(self._change_follow_ups(slots))
            if question == ACCESSORY_QUESTION:
                return ACCESSORY_FOLLOW_UPS
            if "neckline" in q:
                return NECKLINE_FOLLOW_UPS
            if "traditional, minimal or statement" in q:
                return GIFT_STYLE_FOLLOW_UPS
            if "budget" in q:
                return BUDGET_FOLLOW_UPS + INTAKE_FAQS
            if "bangle size" in q:
                return BANGLE_SIZE_FOLLOW_UPS
            if "uk shoe" in q:
                return SHOE_SIZE_FOLLOW_UPS + INTAKE_FAQS
            if "size" in q:
                return SIZE_FOLLOW_UPS + INTAKE_FAQS
            if "running or gym" in q:
                return PRIORITY_FOLLOW_UPS
            if "outfit for" in q or "occasion" in q:
                return [
                    {"title": "Office", "emoji": "💼", "text": "It's for office"},
                    {"title": "Festive", "emoji": "🪔", "text": "It's for a festive occasion"},
                    {"title": "Sports", "emoji": "🏃", "text": "It's for sports or gym"},
                    {"title": "Casual", "emoji": "☀️", "text": "It's for casual everyday wear"},
                ]
            if "colour should i filter" in q:
                return [
                    {"title": "Black", "emoji": "⬛", "text": "Colour black"},
                    {"title": "Navy", "emoji": "🔵", "text": "Colour navy"},
                    {"title": "Gold", "emoji": "🟡", "text": "Colour gold"},
                    {"title": "Skip colour", "text": "No colour preference"},
                ]
            if "human teammate" in q or "live agent" in q:
                return HANDOFF_FOLLOW_UPS
            if "should i compare" in q or "more catalogue product to compare" in q:
                return self._compare_choice_follow_ups(slots)
        if slots.handoff_requested:
            return HANDOFF_FOLLOW_UPS
        if slots.last_products:
            if slots.last_products[0].get("category") == "Footwear":
                return self._with_back(FOOTWEAR_REFINE_FOLLOW_UPS)
            return self._with_back(REFINE_FOLLOW_UPS)
        return []

    def _pack(
        self,
        reply: str,
        slots: ShopperSlots,
        products: Optional[list[dict]] = None,
        question: Optional[str] = None,
        comparison: Optional[dict] = None,
        confirmation: Optional[dict] = None,
    ) -> TurnResult:
        packed = list(products or [])
        if packed and comparison is None and confirmation is None and not slots.checkout_step:
            packed = self._products_named_in_reply(reply, packed)
        if packed:
            slots.last_products = packed
            slots.no_match_streak = 0
            slots.last_blocker = None
            outfit_prices = [int(p["price_inr"]) for p in packed if p.get("category") in ("Ethnic wear", "Western wear") and p.get("price_inr") is not None]
            if outfit_prices:
                slots.last_outfit_prices = outfit_prices
            if question is None:
                slots.last_question_asked = None
        if comparison:
            slots.awaiting_compare = False
            slots.compare_ids = []
        follow_ups = self._follow_ups(slots, question)
        slots.last_follow_ups = follow_ups
        slots.history.append(f"assistant: {reply[:200]}")
        if len(slots.history) > 40:
            slots.history = slots.history[-40:]
        return TurnResult(
            reply=reply,
            products=packed,
            context=slots.to_context_dict(),
            follow_ups=follow_ups,
            intent=slots.intent,
            sentiment=slots.sentiment,
            handoff=slots.handoff_requested,
            comparison=comparison,
            confirmation=confirmation,
        )

    # ------------------------------------------------------------------ questions
    def _needs_occasion(self, slots: ShopperSlots) -> bool:
        if slots.category == "Footwear" or slots.activity:
            return False
        if slots.occasion or slots.recipient:
            return False
        ptype = canonical_product_type(slots.product_type)
        if slots.category in ("Jewellery", "Accessories") or ptype in ACCESSORY_TYPES:
            return False
        if ptype in ("shoes", "sports shoes", "sneakers", "flats", "sandals"):
            return False
        return True

    def _size_kind_needed(self, slots: ShopperSlots) -> Optional[str]:
        ptype = canonical_product_type(slots.product_type)
        if slots.category == "Footwear" or ptype in ("shoes", "sports shoes", "sneakers", "flats", "sandals"):
            return "shoe"
        if ptype == "bangles":
            return "bangle"
        if slots.category in ("Jewellery", "Accessories") or ptype in ACCESSORY_TYPES:
            return None
        return "clothing"

    def _next_question(self, slots: ShopperSlots) -> Optional[str]:
        if RUNNING_AND_GYM.search(f"{slots.activity or ''}") and not slots.outfit_priority:
            return "Is running or gym your main priority for these shoes?"
        if self._needs_occasion(slots):
            return "What is the outfit for — wedding guest, office, party, or something else?"
        if slots.budget_max is None:
            if slots.occasion:
                return f"What is your maximum budget in INR for {slots.occasion}?"
            if slots.product_type:
                return f"What is your maximum budget in INR for {slots.product_type}?"
            if slots.category:
                return f"What is your maximum budget in INR for {slots.category.lower()}?"
            return "What is your maximum budget in INR?"
        kind = self._size_kind_needed(slots)
        if kind and not any(size_kind(s) == kind for s in parse_sizes(slots.size)):
            if kind == "shoe":
                return "What UK shoe size should I look for?"
            if kind == "bangle":
                return "What bangle size should I look for (2.4, 2.6 or 2.8)?"
            return "Which size should I check in the catalogue — XS, S, M, L, XL, XXL, or other?"
        return None

    # ------------------------------------------------------------------ text builders
    def _preference_recap(self, slots: ShopperSlots) -> str:
        lines = slots.preference_lines()
        if not lines:
            return ""
        return "Using your saved preferences: " + " · ".join(lines) + "."

    def _product_payload(self, product: Product, slots: ShopperSlots) -> dict:
        data = product.to_dict()
        data["why"] = explain_match(product, slots)
        data.update(visual_for(product))
        return data

    def _template_recommendations(self, products: list[Product], slots: ShopperSlots) -> str:
        heading = (
            "Here are catalogue options to browse:"
            if slots.intent == "browse"
            else "Here are options from our catalogue:"
        )
        recap = self._preference_recap(slots)
        lines = [f"{recap} {heading}".strip() if recap else heading]
        for p in products:
            why = explain_match(p, slots)
            lines.append(
                f"• {p.product_name} ({p.product_id}) — ₹{p.price_inr}, sizes {p.sizes_raw}, "
                f"{p.stock_status}. {why}"
            )
        return "\n".join(lines)

    def _request_desc(self, slots: ShopperSlots, omit: tuple = ()) -> str:
        """Plain-words summary of the current search, e.g. "gym outfits in size XL"."""
        family = self._family(slots.category, slots.product_type)
        noun = slots.product_type or ("outfits" if slots.scope == "clothing" or family == "clothing" else (slots.category or "products").lower())
        parts = []
        if "colour" not in omit and slots.colour:
            parts.append(slots.colour)
        if "occasion" not in omit and slots.occasion:
            parts.append(slots.occasion)
        if "activity" not in omit and slots.activity:
            parts.append(slots.activity)
        text = " ".join(parts + [noun])
        if "size" not in omit and slots.size:
            text += f" in size {slots.size}"
        if "budget" not in omit and slots.budget_max:
            text += f" under ₹{slots.budget_max}"
        return text

    def _no_match_message(self, slots: ShopperSlots) -> str:
        reason = diagnose_no_match(self.products, slots)
        slots.no_match_streak += 1
        slots.last_blocker = reason
        repeat = slots.no_match_streak >= 2
        omit_map = {"budget": ("budget",), "size": ("size",), "colour": ("colour",), "occasion": ("occasion",), "activity": ("activity",)}
        if reason == "budget":
            wider = filter_products(self.products, _relax(slots, budget_max=None))
            text = f"I couldn't find {self._request_desc(slots, omit_map[reason])} within your maximum budget of ₹{slots.budget_max}."
            if wider:
                cheapest = min(wider, key=lambda p: p.price_inr)
                text += f" The lowest-priced match is {cheapest.product_name} at ₹{cheapest.price_inr}."
            ask = "Raise the budget (e.g. \"make it 5000\") or change another requirement."
        elif reason == "colour":
            wider = filter_products(self.products, _relax(slots, colour=None))
            text = f"I couldn't find {self._request_desc(slots)} in the colour {slots.colour}."
            if wider:
                text += f" Without the colour filter there are {len(wider)} option(s), for example {wider[0].product_name} ({wider[0].colour})."
            ask = "Say \"drop the colour filter\" or pick another colour."
        elif reason == "size":
            wider = filter_products(self.products, _relax(slots, size=None))
            text = f"I couldn't find {self._request_desc(slots, omit_map[reason])} in size {slots.size}."
            if wider:
                text += f" Matching items are listed in: {'; '.join(sorted({p.sizes_raw for p in wider})[:4])}."
            ask = "Tell me another size or say \"drop the size filter\"."
        elif reason in ("activity", "occasion"):
            value = slots.activity if reason == "activity" else slots.occasion
            wider = filter_products(self.products, _relax(slots, **({"activity": None, "outfit_priority": None} if reason == "activity" else {"occasion": None})))
            text = f"I couldn't find {self._request_desc(slots)} — nothing in the catalogue matches {reason} \"{value}\" with your other requirements."
            if wider:
                text += f" Without the {reason} requirement there are {len(wider)} option(s), for example {wider[0].product_name}."
            ask = f"Say \"drop the {reason} filter\" or tell me a different {reason}."
        elif reason == "conflict":
            text = (
                f"Nothing in the catalogue is listed for both the occasion \"{slots.occasion}\" and the activity \"{slots.activity}\" "
                f"({self._request_desc(slots, ('occasion', 'activity'))})."
            )
            ask = f"Which should I keep — {slots.occasion} or {slots.activity}?"
        else:
            active = [x for x in (
                f"occasion {slots.occasion}" if slots.occasion else "",
                f"activity {slots.activity}" if slots.activity else "",
                f"colour {slots.colour}" if slots.colour else "",
                f"size {slots.size}" if slots.size else "",
                f"budget ₹{slots.budget_max}" if slots.budget_max else "",
            ) if x]
            text = f"I couldn't find anything in this catalogue that matches all of: {', '.join(active) or 'your requirements'}."
            ask = "Tell me which one to drop or change."
        if repeat:
            label = "occasion + activity combination" if reason == "conflict" else reason
            text = f"Still no match — the blocker is the {label}, so changing a different requirement won't help. " + text
        return f"{text} {ask}"

    def _change_follow_ups(self, slots: ShopperSlots) -> list[dict]:
        """Chips after an empty search: put the real blocker first."""
        first: list[dict] = []
        blocker = slots.last_blocker
        if blocker == "conflict":
            first = [
                {"title": f"Keep {slots.occasion}", "text": "Drop the activity filter"},
                {"title": f"Keep {slots.activity}", "text": "Drop the occasion filter"},
            ]
        elif blocker in ("activity", "occasion", "colour", "size"):
            value = getattr(slots, blocker)
            first = [{"title": f"Drop {value}"[:30], "emoji": "✂️", "text": f"Drop the {blocker} filter"}]
        return first + list(CHANGE_FOLLOW_UPS)

    DROP_FILTER = re.compile(
        r"\b(?:drop|remove|ignore|forget|clear)\b[^.?!]{0,25}?\b(budget|price|size|colou?rs?|occasion|activity|gym|running|sports?|festive|casual|office|party|wedding|cocktail)\b"
    )

    def _drop_requested(self, parse_text: str, slots: ShopperSlots) -> list:
        """"drop the gym filter" / "remove the colour" -> clear that slot. Returns the cleared fields."""
        m = self.DROP_FILTER.search(parse_text)
        if not m:
            return []
        word = m.group(1)
        cleared = []
        if word in ("budget", "price"):
            slots.budget_max = None
            cleared.append("budget_max")
        elif word == "size":
            slots.size = None
            cleared.append("size")
        elif word.startswith("colo"):
            slots.colour = None
            cleared.append("colour")
        elif word in ("activity", "gym", "running", "sport", "sports"):
            slots.activity = None
            slots.outfit_priority = None
            cleared.append("activity")
        else:
            slots.occasion = None
            cleared.append("occasion")
        return cleared

    def _tone_prefix(self, slots: ShopperSlots) -> str:
        if slots.sentiment == "frustrated":
            return "Sorry this has been frustrating — I'll keep this clear. "
        if slots.sentiment == "confused":
            return "Let me simplify. "
        if slots.sentiment == "excited":
            return "Glad you're into this. "
        return ""

    def _apply_sentiment(self, slots: ShopperSlots, sentiment: str, explicit_handoff: bool) -> None:
        slots.sentiment = sentiment or "neutral"
        if slots.sentiment in {"frustrated", "negative"}:
            slots.frustration_streak += 1
        else:
            slots.frustration_streak = 0  # only consecutive frustration counts
        if explicit_handoff or slots.frustration_streak >= 2:
            slots.handoff_requested = True

    def _resolve_intent(
        self,
        nlu_intent: str,
        parsed: dict,
        accessory_pending: bool,
        text: str,
        slots: Optional[ShopperSlots] = None,
        named_product: bool = False,
    ) -> str:
        grok_intent = str(parsed.get("intent") or "")
        if grok_intent == "compare" and nlu_intent != "compare":
            grok_intent = ""  # never start a comparison the shopper did not ask for
        if slots and slots.awaiting_compare:
            if nlu_intent in {"buy", "handoff"}:
                slots.awaiting_compare = False
                slots.compare_ids = []
            elif nlu_intent == "compare" or named_product:
                return "compare"
            elif nlu_intent == "browse" or SHOP_VERBS.search(text):
                slots.awaiting_compare = False
                slots.compare_ids = []
            else:
                return "compare"
        if nlu_intent in {"compare", "buy", "handoff"}:
            return nlu_intent
        if accessory_pending and len(text.split()) <= 6:
            if NO_WORDS.search(text) and not YES_WORDS.search(text):
                return "accessories_no"
            if YES_WORDS.search(text) and not NO_WORDS.search(text):
                return "accessories_yes"
            if grok_intent in {"accessories_yes", "accessories_no"}:
                return grok_intent
        if grok_intent in {"accessories_yes", "accessories_no", "handoff"}:
            grok_intent = ""  # only meaningful right after the accessory offer / an explicit human request
        if grok_intent in SPECIFIC_INTENTS:
            return grok_intent
        if nlu_intent == "browse":
            return "browse"
        return grok_intent or nlu_intent or "shop"

    # ------------------------------------------------------------------ products named in the message
    def _product_by_id(self, product_id: Optional[str]) -> Optional[Product]:
        if not product_id:
            return None
        return next((p for p in self.products if p.product_id == product_id), None)

    def _products_mentioned(self, message: str) -> list[Product]:
        plain = " " + _plain(message) + " "
        found: list[Product] = []
        for product in self.products:
            pid = " " + product.product_id.lower() + " "
            name = " " + _plain(product.product_name) + " "
            if pid in plain or name in plain:
                found.append(product)
        return found

    def _unique_products(self, products: list[Product]) -> list[Product]:
        seen: set[str] = set()
        unique: list[Product] = []
        for product in products:
            if product.product_id in seen:
                continue
            seen.add(product.product_id)
            unique.append(product)
        return unique

    def _compare_choice_follow_ups(self, slots: ShopperSlots) -> list[dict]:
        selected = [pid for pid in slots.compare_ids if pid]
        chips: list[dict] = []
        for item in slots.last_products:
            pid = str(item.get("product_id") or "")
            if not pid or pid in selected:
                continue
            ids = selected + [pid]
            name = str(item.get("product_name") or pid)
            chips.append(
                {
                    "title": name[:22],
                    "emoji": item.get("emoji") or "🛍️",
                    "text": "compare " + " and ".join(ids),
                }
            )
        return chips[:6]

    def _compare_candidates(self, message: str, slots: ShopperSlots) -> list[Product]:
        mentioned = self._unique_products(self._products_mentioned(message))
        pending = [p for p in (self._product_by_id(pid) for pid in slots.compare_ids) if p]
        combined = self._unique_products(pending + mentioned)
        if len(combined) >= 2:
            return combined[:4]
        if COMPARE_THESE.search(message) and not mentioned and len(slots.last_products) >= 2:
            recovered = [p for p in (self._product_by_id(item.get("product_id")) for item in slots.last_products) if p]
            if len(recovered) >= 2:
                return recovered[:4]
        return combined

    def _compare_table(self, products: list[Product]) -> dict:
        headers = [f"{product.product_name} ({product.product_id})" for product in products]
        rows = []
        for attr, label in COMPARE_FIELDS:
            values = []
            for product in products:
                value = getattr(product, attr)
                if attr == "price_inr":
                    value = f"₹{value}"
                values.append(str(value or "—"))
            if any(value != "—" for value in values):
                rows.append({"label": label, "values": values})
        return {"headers": headers, "rows": rows}

    def _compare_text(self, products: list[Product]) -> str:
        names = " and ".join(f"{p.product_name} ({p.product_id})" for p in products)
        return (
            f"Here's a catalogue-only comparison of {names}. "
            "I won't pick a winner beyond these listed details."
        )

    def _compare_prompt(self, slots: ShopperSlots, selected: list[Product]) -> TurnResult:
        slots.awaiting_compare = True
        slots.compare_ids = [product.product_id for product in selected]
        if selected:
            named = ", ".join(f"{p.product_name} ({p.product_id})" for p in selected)
            text = f"{named} is selected. Type a second catalogue name or ID, or pick one from the shortlist."
            question = COMPARE_MORE_QUESTION
        else:
            text = (
                "I only compare products you name. Type at least two catalogue names or IDs, "
                "tap Compare on two cards, or pick from the shortlist."
            )
            question = COMPARE_QUESTION
        slots.last_question_asked = question
        return self._reply(slots, text, question=question)

    def _buy_product(self, message: str, slots: ShopperSlots) -> Optional[Product]:
        mentioned = self._products_mentioned(message)
        if mentioned:
            return mentioned[0]
        if slots.last_products and (THIS_ONE.search(message) or len(slots.last_products) == 1):
            return self._product_by_id(slots.last_products[0].get("product_id"))
        return None

    def _buy_text(self, product: Product) -> str:
        return checkout.intro(product)

    def _start_checkout(self, product: Product, slots: ShopperSlots) -> TurnResult:
        slots.awaiting_compare = False
        slots.compare_ids = []
        checkout.start(slots, product)
        payload = [self._product_payload(product, slots)]
        question = checkout.question_for(slots.checkout_step)
        slots.last_question_asked = question
        text = checkout.ask_text(product, slots, include_intro=True)
        return self._pack(self._tone_prefix(slots) + text, slots, payload, question=question)

    def _checkout_payload(self, product: Product, slots: ShopperSlots) -> list[dict]:
        return [self._product_payload(product, slots)]

    def _checkout_ask(
        self,
        product: Product,
        slots: ShopperSlots,
        *,
        include_intro: bool = False,
        retry: Optional[str] = None,
    ) -> TurnResult:
        question = checkout.question_for(slots.checkout_step)
        slots.last_question_asked = question
        slots.intent = "buy"
        text = checkout.ask_text(product, slots, include_intro=include_intro, retry=retry)
        return self._pack(self._tone_prefix(slots) + text, slots, self._checkout_payload(product, slots), question=question)

    def _checkout_cancel(self, product: Product, slots: ShopperSlots) -> TurnResult:
        checkout.clear(slots)
        slots.intent = "shop"
        slots.last_question_asked = None
        text = checkout.cancel_text(product)
        return self._pack(self._tone_prefix(slots) + text, slots, self._checkout_payload(product, slots))

    def _checkout_turn(
        self,
        message: str,
        parse_text: str,
        nlu,
        slots: ShopperSlots,
        parsed: dict,
    ) -> Optional[TurnResult]:
        product = self._product_by_id(slots.checkout_product_id)
        if not product:
            checkout.clear(slots)
            return None
        if GO_BACK.match(message):
            checkout.clear(slots)
            return self._go_back(slots)
        if checkout.is_cancel(message):
            return self._checkout_cancel(product, slots)
        if nlu.intent == "buy":
            other = self._buy_product(message, slots)
            if other and other.product_id != product.product_id:
                return self._start_checkout(other, slots)
            return self._checkout_ask(product, slots)
        if nlu.intent in {"compare", "browse", "handoff"} or CHEAPER.search(parse_text) or SIMILAR.search(parse_text):
            checkout.clear(slots)
            return None
        looks_like_question = "?" in message or re.search(
            r"\b(how long|what is|what's|when will|return policy|size chart)\b", parse_text
        )
        if looks_like_question:
            exact_faq = next((f for f in self.faqs if _plain(f.question) == _plain(message)), None)
            faq = exact_faq or match_faq(message, self.faqs, str(parsed.get("faq_topic") or "") or None)
            if faq:
                return self._faq_reply(faq, slots)
        return self._checkout_advance(message, slots, product)

    def _checkout_advance(self, message: str, slots: ShopperSlots, product: Product) -> TurnResult:
        step = slots.checkout_step
        if step == "size":
            size = checkout.parse_size_answer(message, product)
            if not size:
                return self._checkout_ask(
                    product,
                    slots,
                    retry=f"{product.product_name} is listed in {product.sizes_raw}. Pick one of those listed sizes.",
                )
            slots.checkout_size = size
            slots.size = size
            slots.checkout_step = "name"
            return self._checkout_ask(product, slots)
        if step == "name":
            name = checkout.parse_name(message)
            if not name:
                return self._checkout_ask(
                    product,
                    slots,
                    retry=f"I need a name for this order of {product.product_name}.",
                )
            slots.checkout_name = name
            slots.checkout_step = "address"
            return self._checkout_ask(product, slots)
        if step == "address":
            address = checkout.parse_address(message)
            if not address:
                return self._checkout_ask(
                    product,
                    slots,
                    retry=f"Which city should I deliver {product.product_name} to?",
                )
            slots.checkout_address = address
            slots.checkout_step = "payment"
            return self._checkout_ask(product, slots)
        if step == "payment":
            payment = checkout.parse_payment(message)
            if not payment:
                return self._checkout_ask(
                    product,
                    slots,
                    retry=f"Pick UPI, card, or cash on delivery for {product.product_name}.",
                )
            slots.checkout_payment = payment
            slots.checkout_step = "confirm"
            return self._checkout_ask(product, slots)
        if step == "confirm":
            if checkout.is_decline(message):
                return self._checkout_cancel(product, slots)
            if not checkout.is_confirm(message):
                return self._checkout_ask(
                    product,
                    slots,
                    retry=f"Reply yes to place this order of {product.product_name}, or cancel.",
                )
            payload = self._checkout_payload(product, slots)
            extra = payload[0] if payload else {}
            confirmation = checkout.confirmation_payload(product, slots, extra)
            text = checkout.done_text(product)
            checkout.clear(slots)
            slots.intent = "shop"
            slots.last_question_asked = None
            return self._pack(
                self._tone_prefix(slots) + text,
                slots,
                payload,
                confirmation=confirmation,
            )
        checkout.clear(slots)
        return self._checkout_cancel(product, slots)

    def _product_facts(self, product: Product, attrs: list[str], message: str) -> str:
        label = f"{product.product_name} ({product.product_id})"
        parts = []
        wanted_sizes = parse_sizes(message)
        for attr in attrs:
            if attr == "price":
                parts.append(f"{label} is listed at ₹{product.price_inr}.")
            elif attr == "material":
                parts.append(f"{label} — material: {product.material}.")
            elif attr == "care":
                parts.append(f"{label} — care: {product.care_instructions}.")
            elif attr == "sizes":
                if wanted_sizes:
                    ok = [s for s in wanted_sizes if size_matches(product, s)]
                    bad = [s for s in wanted_sizes if s not in ok]
                    if ok:
                        parts.append(f"{label} — {', '.join(ok)} is covered by the listed sizes ({product.sizes_raw}).")
                    if bad:
                        parts.append(f"{label} — {', '.join(bad)} is not listed (sizes: {product.sizes_raw}).")
                else:
                    parts.append(f"{label} — listed sizes: {product.sizes_raw}.")
            elif attr == "stock":
                parts.append(f"{label} — sample stock status: {product.stock_status}. This is sample catalogue data, not live stock.")
            elif attr == "colour":
                parts.append(f"{label} — colour: {product.colour}.")
            elif attr == "occasion":
                parts.append(f"{label} — listed for: {product.occasions}.")
            elif attr == "features":
                parts.append(
                    f"{label}: {product.colour}, {product.material}; {product.key_features}; sizes {product.sizes_raw}; "
                    f"₹{product.price_inr}; {product.stock_status}; listed for {product.occasions}."
                )
        return " ".join(parts)

    def _product_question(self, message: str, parse_text: str, slots: ShopperSlots, nlu_intent: str) -> Optional[TurnResult]:
        """Answer price/material/care/size/stock questions about a product named in the message
        (or the ones just shown) straight from the catalogue row - no LLM involved."""
        lower = parse_text
        if nlu_intent in {"compare", "buy"} or slots.awaiting_compare or SIMILAR.search(lower) or CHEAPER.search(lower):
            return None
        attrs = [name for name, pattern in ATTRIBUTE_PATTERNS if pattern.search(lower)]
        named = self._products_mentioned(message)
        targets: list[Product] = list(named)
        if not targets:
            if not attrs or not REFERENT.search(lower) or SHOP_VERBS.search(lower) or not slots.last_products:
                return None
            recovered = [self._product_by_id(p.get("product_id")) for p in slots.last_products]
            recovered = [p for p in recovered if p]
            picked = None
            for word, idx in ORDINALS.items():
                if re.search(rf"\b{word}\b", lower) and recovered:
                    picked = [recovered[idx]] if (idx == -1 or idx < len(recovered)) else None
                    break
            targets = picked or recovered[:3]
        if not targets:
            return None
        if not attrs:
            if len(named) == 1 and len(lower.split()) <= 9 and not re.search(r"\b(buy|similar|compare|cheaper)\b", lower):
                attrs = ["features"]
            else:
                return None
        targets = targets[:3]
        text = " ".join(self._product_facts(p, attrs, message) for p in targets)
        slots.intent = "faq"
        payload = [self._product_payload(p, slots) for p in targets]
        return self._pack(self._tone_prefix(slots) + text, slots, payload)

    # ------------------------------------------------------------------ faq / off-catalogue / smalltalk
    def _faq_reply(self, faq: FAQ, slots: ShopperSlots) -> TurnResult:
        text = faq.answer
        q = faq.question.lower()
        if slots.last_products:
            shown = [self._product_by_id(p.get("product_id")) for p in slots.last_products]
            shown = [p for p in shown if p]
            if "in stock" in q and shown:
                text += " Sample status for the items above: " + "; ".join(f"{p.product_name} — {p.stock_status}" for p in shown) + "."
            elif ("wash this dress" in q or "care for" in q) and shown:
                text += " For the items above: " + "; ".join(f"{p.product_name} — {p.care_instructions}" for p in shown) + "."
        slots.intent = "faq"
        pending = slots.last_question_asked
        if not pending and self._has_active_request(slots):
            pending = self._next_question(slots)
        if pending and "human teammate" in pending.lower():
            pending = None
        if pending:
            if pending != ACCESSORY_QUESTION:  # the accessory offer is made once; keep its chips but do not repeat it
                text += f"\n\n{pending}"
            slots.last_question_asked = pending
        return self._reply(slots, text, question=pending)

    @staticmethod
    def _has_active_request(slots: ShopperSlots) -> bool:
        return bool(slots.occasion or slots.activity or slots.category or slots.product_type or slots.budget_max or slots.recipient)

    def _off_catalogue(self, message: str, parse_text: str, nlu, parsed: dict) -> Optional[str]:
        lower = parse_text
        supported = requested_product_type(lower)
        word = None
        m = UNSUPPORTED.search(lower)
        if m:
            word = m.group(1)
            if word in MEN_WORDS and supported in ("shoes", "sports shoes", "sneakers", "flats", "sandals"):
                return None  # the catalogue does list men's/unisex shoes
            if word in MEN_WORDS or not supported:
                return word
        if parsed.get("off_catalogue") is True and not supported and not nlu.slots.get("category"):
            return "that"
        raw_type = parsed.get("product_type")
        if raw_type and canonical_product_type(raw_type) is None:
            plain = _plain(str(raw_type))
            generic = {"outfit", "outfits", "clothing", "clothes", "apparel", "wear", "casual outfits", "office wear", "dress up"}
            if plain and plain not in generic and not any(plain in _plain(p.product_type + " " + p.product_name) for p in self.products):
                if not canonical_category(parsed.get("category")) and not nlu.slots.get("category") and not supported:
                    if not re.search(r"\b(outfit|wear|clothes?|clothing|attire|look)\b", plain):
                        return plain
        return None

    def _off_catalogue_reply(self, slots: ShopperSlots, thing: str) -> TurnResult:
        label = "men's clothing" if thing in MEN_WORDS else (thing if thing != "that" else "that")
        text = (
            f"I don't have {label} in this catalogue. I can help with women's ethnic and western outfits, jewellery, "
            "watches, bags and clutches, and footwear. What would you like to look at?"
        )
        slots.intent = "faq"
        return self._reply(slots, text)

    # ------------------------------------------------------------------ handoff
    def _handoff_pack(self, slots: ShopperSlots) -> TurnResult:
        slots.intent = "handoff"
        slots.handoff_requested = True
        slots.frustration_streak = 0  # one handoff notice, then back to normal shopping
        slots.last_question_asked = (
            "I've flagged this for a human teammate. Want to keep using the catalogue assistant?"
        )
        return self._pack(self._tone_prefix(slots) + HANDOFF_REPLY, slots, question=slots.last_question_asked)

    def _reply(self, slots: ShopperSlots, text: str, products: Optional[list[dict]] = None, question: Optional[str] = None) -> TurnResult:
        return self._pack(self._tone_prefix(slots) + text, slots, products, question)

    # ------------------------------------------------------------------ LLM wording (always guarded)
    def _grok_instruction(self, slots: ShopperSlots, instruction: str) -> str:
        return (
            f"Shopper intent is {slots.intent}. Sentiment is {slots.sentiment}. {instruction} "
            "Use ONLY the catalogue records provided (from the Excel sheet). "
            "Do not invent products, prices, sizes, or stock. "
            "If a product is not in the list, do not mention it. "
            "Name every provided product on its own • line, in the given order. "
            "Do not skip, replace, or reorder them — the product cards follow this list."
        )

    def _is_answering_intake(self, slots: ShopperSlots, change_field: str) -> bool:
        q = (slots.last_question_asked or "").lower()
        field_name = (change_field or "").lower()
        if not q or "requirement" in q:
            return False
        if field_name == "occasion" and ("outfit for" in q or "occasion" in q):
            return True
        if field_name in {"budget", "budget_max"} and "budget" in q:
            return True
        if field_name == "size" and "size" in q:
            return True
        if field_name in {"colour", "color"} and "colour should i filter" in q:
            return True
        return False

    def _products_named_in_reply(self, reply: str, product_dicts: list[dict]) -> list[dict]:
        """Cards follow the products actually named in the reply, in mention order."""
        text = (reply or "").lower()
        hits: list[tuple[int, dict]] = []
        for product in product_dicts:
            name = str(product.get("product_name") or "").strip().lower()
            pid = str(product.get("product_id") or "").strip().lower()
            idx = text.find(name) if name else -1
            if pid:
                pid_idx = text.find(pid)
                if pid_idx != -1 and (idx == -1 or pid_idx < idx):
                    idx = pid_idx
            if idx != -1:
                hits.append((idx, product))
        hits.sort(key=lambda item: item[0])
        seen: set[str] = set()
        ordered: list[dict] = []
        for _, product in hits:
            pid = str(product.get("product_id") or "")
            if pid and pid not in seen:
                seen.add(pid)
                ordered.append(product)
        return ordered

    def _reply_uses_only_catalogue(self, reply: str, product_dicts: list[dict]) -> bool:
        allowed = {str(p.get("product_id") or "") for p in product_dicts}
        mentioned = re.findall(r"\b([FJSA]\d{3})\b", reply)
        if any(pid not in allowed for pid in mentioned):
            return False
        allowed_names = {str(p.get("product_name") or "").lower() for p in product_dicts if p.get("product_name")}
        for product in self.products:
            name = product.product_name.lower()
            if name and name in reply.lower() and product.product_id not in allowed:
                if name not in allowed_names:
                    return False
        return True

    def _reply_covers_shortlist(self, reply: str, product_dicts: list[dict]) -> bool:
        if not product_dicts:
            return True
        named = {p.get("product_id") for p in self._products_named_in_reply(reply, product_dicts)}
        return all(p.get("product_id") in named for p in product_dicts)

    def _catalogue_reply(
        self,
        slots: ShopperSlots,
        product_dicts: list[dict],
        instruction: str,
        fallback: str,
        user_text: str = "",
    ) -> str:
        if not product_dicts:
            return fallback
        if not self.grok.available:
            return fallback
        try:
            reply = self.grok.compose_reply(
                slots.to_context_dict(),
                product_dicts,
                self._grok_instruction(slots, instruction),
            )
        except Exception as exc:
            logger.warning("LLM reply failed (%s); using template", type(exc).__name__)
            return fallback
        reply = guards.strip_markdown(reply or "")
        if not self._reply_uses_only_catalogue(reply, product_dicts):
            self.last_guard_failure = "unknown product"
            return fallback
        if not self._reply_covers_shortlist(reply, product_dicts):
            self.last_guard_failure = "shortlist mismatch"
            logger.info("LLM reply omitted shortlist items; using template")
            return fallback
        problem = guards.violation(reply, product_dicts, slots.budget_max, user_text)
        if problem:
            self.last_guard_failure = problem
            logger.info("LLM reply rejected (%s); using template", problem)
            return fallback
        return guards.ensure_low_stock_noted(reply, product_dicts)

    def _apply_memory_refinements(self, message: str, slots: ShopperSlots, updates: Optional[dict] = None) -> bool:
        """"cheaper" / "similar" follow-ups. Returns True when the request was a similar-to-shown one."""
        similar = False
        if CHEAPER.search(message) and slots.last_products:
            prices = [int(p["price_inr"]) for p in slots.last_products if p.get("price_inr") is not None]
            updates = updates or {}
            asks_clothing = self._family(updates.get("category", slots.category), updates.get("product_type", slots.product_type)) == "clothing"
            if asks_clothing and slots.last_outfit_prices and not any(
                p.get("category") in ("Ethnic wear", "Western wear") for p in slots.last_products
            ):
                prices = list(slots.last_outfit_prices)  # accessories were shown last, but the shopper wants cheaper outfits
            if prices:
                cap = max(50, min(prices) - 1)
                slots.budget_max = min(slots.budget_max, cap) if slots.budget_max else cap
        named = self._products_mentioned(message)
        if SIMILAR.search(message) and (slots.last_products or named):
            first = self._product_by_id(slots.last_products[0].get("product_id")) if slots.last_products else None
            seed = named[0] if named else first
            if seed:
                similar = True
                slots.avoid_ids = [seed.product_id]
                if not slots.category:
                    slots.category = seed.category
                if not slots.style and seed.style_tags:
                    slots.style = normalize_style(seed.style_tags.split(";")[0]) or None
        return similar

    # ------------------------------------------------------------------ styling persona
    DIRECTIONS = (
        "• Antique gold — a traditional contrast\n"
        "• Pearls — a softer look\n"
        "• Rose gold — a subtle, modern finish"
    )

    def _styling_applies(self, slots: ShopperSlots) -> bool:
        ptype = canonical_product_type(slots.product_type)
        is_jewellery = slots.category == "Jewellery" or ptype in {"jewellery", "necklace", "earrings", "bracelet", "bangles"}
        return bool(is_jewellery and slots.outfit_colour)

    def _styling_pick(self, slots: ShopperSlots, ptype: str, limit: int) -> list[Product]:
        probe = ShopperSlots(
            category="Jewellery",
            product_type=ptype,
            budget_max=slots.budget_max,
            occasion=None,
            style=None,
        )
        found = filter_products(self.products, probe, include_accessories=True)

        def direction_rank(p: Product) -> tuple:
            text = (p.colour + " " + p.product_name + " " + p.material).lower()
            if "antique gold" in text:
                rank = 0
            elif "pearl" in text:
                rank = 1
            elif "rose gold" in text:
                rank = 2
            elif "gold" in text:
                rank = 3
            else:
                rank = 4
            return (rank, p.price_inr, p.product_id)

        return sorted(found, key=direction_rank)[:limit]

    def _styling_turn(self, slots: ShopperSlots) -> TurnResult:
        colour = slots.outfit_colour or "outfit"
        asked_type = canonical_product_type(slots.product_type)
        wants_earrings_only = asked_type == "earrings"
        slots.intent = "shop"
        intro = (
            f"Here are a few styling directions for your {colour} outfit. These are personal options, "
            f"not fixed rules for any skin tone:\n{self.DIRECTIONS}"
        )
        faq4 = next((f for f in self.faqs if f.question.lower().startswith("what jewellery goes with a peach dress")), None)
        if faq4 and "peach" in colour:
            intro += f"\n\n{faq4.answer}"
        if slots.neckline is None and not wants_earrings_only:
            picks = self._styling_pick(slots, "earrings", 3)
            dicts = [self._product_payload(p, slots) for p in picks]
            lines = [f"• {p.product_name} ({p.product_id}) — ₹{p.price_inr}, {p.colour}, {p.stock_status}" for p in picks]
            body = intro
            if lines:
                body += "\n\nEarrings from the catalogue in those directions:\n" + "\n".join(lines)
            body += f"\n\nBefore I suggest a necklace: {NECKLINE_QUESTION}"
            body = guards.ensure_low_stock_noted(body, dicts)
            slots.last_question_asked = NECKLINE_QUESTION
            return self._reply(slots, body, dicts, question=NECKLINE_QUESTION)
        ptype = "earrings" if wants_earrings_only else "necklace"
        picks = self._styling_pick(slots, ptype, 3)
        if not picks:
            slots.last_question_asked = CHANGE_REQUIREMENT_QUESTION
            return self._reply(
                slots,
                f"I couldn't find a {ptype} within your jewellery budget in this catalogue. {CHANGE_REQUIREMENT_QUESTION}",
                question=CHANGE_REQUIREMENT_QUESTION,
            )
        dicts = [self._product_payload(p, slots) for p in picks]
        lines = [f"• {p.product_name} ({p.product_id}) — ₹{p.price_inr}, {p.colour}, {p.material}, {p.stock_status}" for p in picks]
        faq24 = next((f for f in self.faqs if f.question.lower().startswith("how should i choose a necklace")), None)
        neck = ""
        if slots.neckline and slots.neckline != "not specified":
            neck = f"For your {slots.neckline}, "
        body = f"{neck}these {ptype}{'' if ptype.endswith('s') else 's'} from the catalogue fit the antique gold / pearl / rose gold directions:\n" + "\n".join(lines)
        if faq24 and ptype == "necklace":
            body += f"\n\n{faq24.answer.split('Share')[0].strip()}"
        if slots.budget_max is None:
            body += "\n\nShare a jewellery budget if you'd like me to narrow these down."
        body = guards.ensure_low_stock_noted(body, dicts)
        slots.last_question_asked = None
        return self._reply(slots, body, dicts)

    # ------------------------------------------------------------------ main entry points
    def handle_message(self, chat_id: str, message: str, slots: ShopperSlots) -> str:
        return self.handle_turn(chat_id, message, slots).reply

    def _mask_product_names(self, message: str) -> str:
        masked = message
        for product in self.products:
            masked = re.sub(re.escape(product.product_name), " ", masked, flags=re.I)
            masked = re.sub(rf"\b{re.escape(product.product_id)}\b", " ", masked, flags=re.I)
        return masked

    @staticmethod
    def _clean_message(message: str) -> str:
        message = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", message or "")
        return message.strip()[:MAX_MESSAGE_CHARS]

    def handle_turn(self, chat_id: str, message: str, slots: ShopperSlots) -> TurnResult:
        message = self._clean_message(message)
        slots.canonicalise()  # sessions saved by older code may hold raw values ("clothing", "outfit"...)
        if not message:
            return TurnResult(
                "Tell me what you're looking for and I'll search the catalogue.",
                context=slots.to_context_dict(),
            )

        slots.history.append(f"user: {message[:300]}")
        slots.handoff_requested = False
        named_products = self._products_mentioned(message)
        # a product name such as "Aarohi Peach Anarkali" must not be read as a colour/type request
        masked = self._mask_product_names(message) if named_products else message
        nlu = understand(masked)
        parse_text = nlu.corrected or message.lower()
        parsed = {} if slots.checkout_step else self._llm_parse(masked if named_products else message, slots)

        # ---- human handoff: explicit request (regex) or repeated frustration; never on an LLM guess alone
        explicit_handoff = bool(nlu.handoff or nlu.intent == "handoff")
        self._apply_sentiment(slots, str(parsed.get("sentiment") or nlu.sentiment), explicit_handoff)
        if "catalogue help" in parse_text:
            slots.handoff_requested = False
            slots.frustration_streak = 0
            explicit_handoff = False
        elif slots.handoff_requested:
            return self._handoff_pack(slots)

        accessory_pending = slots.last_question_asked == ACCESSORY_QUESTION

        # ---- turns that never change the shopper's saved preferences
        if GREETING.match(message):
            slots.intent = "shop"
            pending_q = slots.last_question_asked
            if pending_q and "human teammate" not in pending_q.lower():
                return self._reply(slots, f"Hi again! Where we left off: {pending_q}", question=pending_q)
            return self._reply(
                slots,
                "Hi! I can shortlist women's ethnic and western outfits, jewellery, watches, bags and footwear "
                "from our catalogue. What are you looking for?",
            )
        if slots.checkout_step:
            checkout_result = self._checkout_turn(message, parse_text, nlu, slots, parsed)
            if checkout_result is not None:
                return checkout_result
        if GO_BACK.match(message):
            return self._go_back(slots)
        if THANKS.match(message) and not slots.last_question_asked:
            return self._reply(slots, "You're welcome! Tell me if you'd like to refine the shortlist or look at something else.")
        exact_faq = next((f for f in self.faqs if _plain(f.question) == _plain(message)), None)
        if exact_faq and not slots.awaiting_compare:
            return self._faq_reply(exact_faq, slots)
        styling_request = bool(self.STYLING_CUE.search(parse_text))
        if not styling_request:
            product_answer = self._product_question(message, parse_text, slots, nlu.intent)
            if product_answer:
                return product_answer
            yes_no_reply = accessory_pending and len(message.split()) <= 6 and bool(YES_WORDS.search(parse_text) or NO_WORDS.search(parse_text))
            if not yes_no_reply and not slots.awaiting_compare:
                faq = match_faq(message, self.faqs, str(parsed.get("faq_topic") or "") or None)
                if faq:
                    return self._faq_reply(faq, slots)
        off = self._off_catalogue(message, parse_text, nlu, parsed)
        if off:
            return self._off_catalogue_reply(slots, off)

        # ---- update the shopper's brief
        updates = self._extract_updates(message, parse_text, nlu, parsed, slots)
        if accessory_pending and (YES_WORDS.search(parse_text) or NO_WORDS.search(parse_text)) and len(parse_text.split()) <= 6:
            updates = {k: v for k, v in updates.items() if k in {"budget_max"}}
        change_field = self._detect_change_field(parse_text, slots, parsed)
        if not change_field and parsed.get("intent") == "change_requirement" and parsed.get("change_field"):
            change_field = str(parsed.get("change_field")).lower()
            if change_field in {"budget_max"}:
                change_field = "budget"
            if change_field not in {"budget", "size", "colour", "occasion"}:
                change_field = ""
        answering_intake = self._is_answering_intake(slots, change_field)
        if answering_intake:
            change_field = ""
        if self._answer_is_colour_skip(parse_text, slots):
            slots.colour = None
            slots.last_question_asked = None
            updates.pop("colour", None)
        if slots.last_question_asked and "neckline" in slots.last_question_asked.lower() and "neckline" not in updates:
            if re.search(r"\b(skip|not sure|no idea|dont know|do not know|any)\b", parse_text):
                updates["neckline"] = "not specified"
            elif re.search(r"\b(neck|collar|strapless|halter|off shoulder)\b", parse_text):
                updates["neckline"] = clean_text(parse_text, 30) or "not specified"
        similar = self._apply_memory_refinements(message, slots, updates)
        dropped = self._drop_requested(parse_text, slots)
        for key in dropped:  # "drop the gym filter" must not be re-read as "gym"
            updates.pop(key, None)
            if key == "activity":
                updates.pop("outfit_priority", None)
            if key == "budget_max":
                updates.pop("budget_max", None)
        if dropped:
            change_field = ""
        self._apply_updates(slots, updates)
        cleared = self._apply_requirement_change(change_field, updates, slots) if not answering_intake else False
        colour_reset = cleared and change_field == "colour"

        intent = self._resolve_intent(
            nlu.intent, parsed, accessory_pending, parse_text, slots, bool(named_products)
        )
        if intent == "buy" and not self._buy_product(message, slots):
            intent = "shop"
        slots.intent = intent if intent in SPECIFIC_INTENTS or intent == "shop" else "shop"

        if colour_reset and not slots.colour:
            question = "Which colour should I filter for?"
            slots.last_question_asked = question
            return self._reply(slots, "Which colour should I filter for, or say skip?", question=question)

        if intent == "compare":
            candidates = self._compare_candidates(message, slots)
            if len(candidates) < 2:
                return self._compare_prompt(slots, candidates)
            product_dicts = [self._product_payload(p, slots) for p in candidates]
            table = self._compare_table(candidates)
            reply = self._tone_prefix(slots) + self._compare_text(candidates)
            return self._pack(reply, slots, product_dicts, comparison=table)

        if intent == "buy":
            target = self._buy_product(message, slots)
            if target:
                return self._start_checkout(target, slots)

        if intent == "accessories_yes" and accessory_pending:
            slots.last_question_asked = None
            acc = accessory_products(self.products, slots)
            if not acc:
                return self._reply(
                    slots,
                    "I couldn't find matching jewellery or clutches within your budget. Want to adjust the budget?",
                )
            product_dicts = [self._product_payload(p, slots) for p in acc]
            fallback = self._template_recommendations(acc, slots)
            reply = self._catalogue_reply(
                slots,
                product_dicts,
                "Shopper accepted accessories. Suggest the 1-3 complementary pieces from the list (jewellery and a clutch or tote).",
                fallback,
                message,
            )
            return self._pack(reply, slots, product_dicts)

        if intent == "accessories_no" and accessory_pending:
            slots.last_question_asked = None
            return self._reply(slots, "No problem. Tell me if you'd like to refine the outfit shortlist.")

        if accessory_pending:
            slots.last_question_asked = None  # the shopper moved on; the offer is not repeated

        if self._styling_applies(slots):
            styled = self._styling_turn(slots)
            if styled is not None:
                return styled

        question = None if similar else self._next_question(slots)
        if question:
            slots.last_question_asked = question
            return self._reply(slots, question, question=question)

        is_jewellery_request = canonical_category(slots.category) == "Jewellery" or canonical_product_type(slots.product_type) == "jewellery"
        shortlist = rank_products(
            filter_products(self.products, slots, include_accessories=False),
            slots,
            limit=3,
            diverse=is_jewellery_request and not canonical_product_type(slots.product_type) in {"necklace", "earrings", "bracelet", "bangles"},
            prefer_higher_price=bool(slots.recipient),
        )
        slots.avoid_ids = []
        if not shortlist:
            slots.last_question_asked = CHANGE_REQUIREMENT_QUESTION
            return self._reply(slots, self._no_match_message(slots), question=CHANGE_REQUIREMENT_QUESTION)

        is_outfit = any(p.category in ("Ethnic wear", "Western wear") for p in shortlist)
        offer_now = is_outfit and not slots.offered_accessories
        if offer_now:
            slots.offered_accessories = True
            instruction = (
                "Present the outfit shortlist (2-3 items). End by asking once if they want "
                "matching jewellery or a clutch. Do not add accessories yet."
            )
        else:
            instruction = (
                "Present the shortlist. For each product, use its why field to explain the match "
                "in one short phrase. Mention saved preferences only if they appear in that why field."
            )
        if any(p.category == "Footwear" for p in shortlist) and len(shortlist) > 1:
            instruction += " Add one short trade-off note (price, listed features or tags only); no health or injury claims."
        product_dicts = [self._product_payload(p, slots) for p in shortlist]
        base = self._template_recommendations(shortlist, slots)
        if offer_now:
            base += f"\n\n{ACCESSORY_QUESTION}"
        reply = self._catalogue_reply(slots, product_dicts, instruction, base, message)
        notes = []
        if offer_now and "jewellery" not in reply.lower().split("\n")[-1].lower():
            notes.append(ACCESSORY_QUESTION)
        bangles = [p for p in shortlist if re.search(r"\d\.\d", p.sizes_raw)]
        if bangles and "bangle" not in (slots.last_question_asked or ""):
            names = ", ".join(p.product_name for p in bangles)
            notes.append(f"Note: {names} come in bangle sizes {bangles[0].sizes_raw}, so you'd need to know the right bangle size.")
        gift_question = None
        if slots.recipient and not slots.style and not slots.style_asked and any(p.category == "Jewellery" for p in shortlist):
            slots.style_asked = True
            gift_question = GIFT_STYLE_QUESTION
            notes.append(gift_question)
        if notes:
            reply = reply.rstrip() + "\n\n" + "\n".join(notes)
        question_out = ACCESSORY_QUESTION if offer_now else gift_question
        if question_out:
            slots.last_question_asked = question_out
        return self._pack(reply, slots, product_dicts, question=question_out)


def _relax(slots: ShopperSlots, **kwargs) -> ShopperSlots:
    from dataclasses import replace

    return replace(slots, **kwargs)
