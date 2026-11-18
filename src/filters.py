from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import List, Optional

from src.catalogue import Product
from src.normalize import (
    canonical_category,
    canonical_product_type,
    normalize_activity,
    normalize_category_and_type,
    normalize_colour,
    normalize_occasion,
    normalize_size,
    normalize_style,
    parse_sizes,
    size_kind,
    TYPE_ALIASES,
)

CLOTHING_SIZES = {"XS", "S", "M", "L", "XL", "XXL", "XXXL"}


@dataclass
class ShopperSlots:
    intent: str = "shop"
    category: Optional[str] = None
    product_type: Optional[str] = None
    occasion: Optional[str] = None
    activity: Optional[str] = None
    budget_max: Optional[int] = None
    size: Optional[str] = None
    colour: Optional[str] = None
    style: Optional[str] = None
    metal: Optional[str] = None
    look: Optional[str] = None
    wants_accessories: Optional[bool] = None
    outfit_priority: Optional[str] = None  # running vs gym when both mentioned
    offered_accessories: bool = False
    last_question_asked: Optional[str] = None
    last_follow_ups: list[dict] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    sentiment: str = "neutral"
    frustration_streak: int = 0
    handoff_requested: bool = False
    last_products: list[dict] = field(default_factory=list)
    awaiting_compare: bool = False  # shopper asked to compare but has not named two items yet
    compare_ids: list[str] = field(default_factory=list)  # product IDs already chosen for comparison
    outfit_colour: Optional[str] = None  # colour of an outfit the shopper already owns (styling), NOT a product filter
    neckline: Optional[str] = None
    recipient: Optional[str] = None  # gift recipient, e.g. mother
    avoid_ids: list[str] = field(default_factory=list)  # transient: products to leave out of the next shortlist
    last_outfit_prices: list[int] = field(default_factory=list)  # prices of the last clothing shortlist (for "cheaper")
    scope: Optional[str] = None  # "clothing" when the shopper asked for "outfits"/"clothes" without naming a type
    no_match_streak: int = 0  # consecutive turns that found nothing (to stop "change a requirement" loops)
    last_blocker: Optional[str] = None  # the constraint that blocked the last empty search
    style_asked: bool = False  # gift flow: the traditional/minimal/statement question was already asked once
    checkout_step: Optional[str] = None  # size | name | address | payment | confirm; live only, never saved
    checkout_product_id: Optional[str] = None
    checkout_size: Optional[str] = None
    checkout_name: Optional[str] = None
    checkout_address: Optional[str] = None
    checkout_payment: Optional[str] = None

    def canonicalise(self) -> None:
        """Re-validate every saved value so sessions written by older code (category "clothing",
        product_type "outfit", size "M or L"...) cannot keep a search broken."""
        raw = f"{self.category or ''} {self.product_type or ''}".lower()
        cat, ptype = normalize_category_and_type(self.category, self.product_type)
        if not cat and not ptype and not self.scope and re.search(r"\b(cloth\w*|outfits?|apparel|wear)\b", raw):
            self.scope = "clothing"
        self.category, self.product_type = cat, ptype
        self.occasion = (normalize_occasion(self.occasion) or None) if self.occasion else None
        self.activity = (normalize_activity(self.activity) or None) if self.activity else None
        self.colour = (normalize_colour(self.colour) or None) if self.colour else None
        self.style = (normalize_style(self.style) or None) if self.style else None
        self.size = (normalize_size(self.size) or None) if self.size else None
        try:
            self.budget_max = int(self.budget_max) if self.budget_max is not None else None
        except (TypeError, ValueError):
            self.budget_max = None
        if self.scope not in (None, "clothing"):
            self.scope = None
        if not isinstance(self.avoid_ids, list):
            self.avoid_ids = []
        if not isinstance(self.compare_ids, list):
            self.compare_ids = []
        self.awaiting_compare = bool(self.awaiting_compare)

    def merge(self, updates: dict) -> None:
        for key, value in updates.items():
            if value is None:
                continue
            if key == "wants_accessories" and isinstance(value, bool):
                setattr(self, key, value)
                continue
            if hasattr(self, key) and key not in {
                "history",
                "last_follow_ups",
                "last_products",
                "avoid_ids",
                "last_outfit_prices",
                "compare_ids",
                "awaiting_compare",
                "checkout_step",
                "checkout_product_id",
                "checkout_size",
                "checkout_name",
                "checkout_address",
                "checkout_payment",
            }:
                setattr(self, key, value)

    def to_context_dict(self) -> dict:
        last_ids = [p.get("product_id") for p in self.last_products if p.get("product_id")]
        return {
            k: v
            for k, v in {
                "intent": self.intent,
                "category": self.category,
                "product_type": self.product_type,
                "occasion": self.occasion,
                "activity": self.activity,
                "budget_max": self.budget_max,
                "size": self.size,
                "colour": self.colour,
                "style": self.style,
                "metal": self.metal,
                "look": self.look,
                "wants_accessories": self.wants_accessories,
                "outfit_priority": self.outfit_priority,
                "outfit_colour": self.outfit_colour,
                "neckline": self.neckline,
                "recipient": self.recipient,
                "last_question_asked": self.last_question_asked,
                "sentiment": self.sentiment,
                "handoff_requested": self.handoff_requested,
                "saved_preferences": self.preference_lines(),
                "recent_history": self.history[-8:],
                "last_product_ids": last_ids,
            }.items()
            if v is not None and v != []
        }

    def preference_lines(self) -> list[str]:
        labels = [
            ("occasion", "Occasion"),
            ("activity", "Activity"),
            ("category", "Category"),
            ("product_type", "Type"),
            ("budget_max", "Budget"),
            ("size", "Size"),
            ("colour", "Colour"),
            ("style", "Style"),
            ("outfit_priority", "Priority"),
            ("outfit_colour", "Your outfit colour"),
            ("neckline", "Neckline"),
            ("recipient", "Gift for"),
        ]
        lines: list[str] = []
        for key, label in labels:
            value = getattr(self, key)
            if value is None:
                continue
            if key == "budget_max":
                value = f"₹{value}"
            lines.append(f"{label}: {value}")
        return lines


def normalize_size_token(size: str) -> str:
    return size.strip().upper().replace("UK ", "UK")


def parse_shoe_range(sizes_raw: str) -> list[tuple[int, int]]:
    """Parse 'UK 4–8' or 'UK 3-8' into list of (min, max) ranges."""
    ranges: list[tuple[int, int]] = []
    text = sizes_raw.replace("–", "-").replace("—", "-")
    for part in re.split(r"[;,]", text):
        part = part.strip()
        m = re.search(r"UK\s*(\d+)\s*-\s*(\d+)", part, re.I)
        if m:
            ranges.append((int(m.group(1)), int(m.group(2))))
    return ranges


def size_matches(product: Product, shopper_size: Optional[str]) -> bool:
    """True if ``product`` is listed in (any of) the shopper's size(s).

    The shopper may give several sizes ("M or L"). A size that cannot apply to the product kind
    (a UK shoe size for a dress, say) is ignored rather than rejecting the product.
    """
    wanted = parse_sizes(shopper_size)
    if not wanted:
        return True
    raw = product.sizes_raw
    lower = raw.lower()
    if "one size" in lower or "free size" in lower or "adjustable" in lower:
        return True

    if product.category == "Footwear":
        uks = [float(s.split()[1]) for s in wanted if size_kind(s) == "shoe"]
        if not uks:
            return True
        ranges = parse_shoe_range(raw)
        return any(lo <= uk <= hi for uk in uks for lo, hi in ranges)

    bangle_sizes = re.findall(r"\d+\.\d+", raw)
    if bangle_sizes:
        wanted_b = [s for s in wanted if size_kind(s) == "bangle"]
        if not wanted_b:
            return True
        return any(abs(float(w) - float(n)) < 0.01 for w in wanted_b for n in bangle_sizes)

    wanted_c = [s for s in wanted if size_kind(s) == "clothing"]
    if not wanted_c:
        return True
    tokens = {t.strip().upper() for t in re.split(r"[,;/]", raw) if t.strip()}
    return any(w in tokens for w in wanted_c)


def listed_sizes_for(product: Product, shopper_size: Optional[str]) -> List[str]:
    """Which of the shopper's sizes are explicitly listed for this product (for explanations)."""
    wanted = parse_sizes(shopper_size)
    if not wanted:
        return []
    lower = product.sizes_raw.lower()
    if "one size" in lower or "free size" in lower or "adjustable" in lower:
        return []
    return [w for w in wanted if size_matches(product, w)]


def budget_matches(product: Product, budget_max: Optional[int]) -> bool:
    if budget_max is None:
        return True
    return product.price_inr <= budget_max


def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[a-z0-9]+", text.lower())}


_OCCASION_EXPAND = {
    "cocktail": {"cocktail", "party", "evening"},
    "party": {"party", "cocktail", "evening"},
    "wedding": {"wedding", "reception"},
    "casual": {"casual"},
    "daily": {"daily"},
    "office": {"office"},
    "festive": {"festive"},
    "brunch": {"brunch", "daytime"},
    "dinner": {"dinner"},
    "travel": {"travel", "holiday"},
    "college": {"college"},
}
_ACTIVITY_EXPAND = {
    "running": {"running"},
    "gym": {"gym", "training"},
    "sports": {"sports", "running", "gym", "training"},
    "walking": {"walking"},
    "trail": {"trail", "trails", "outdoor"},
}


def _product_occasion_tokens(product: Product) -> set[str]:
    return _tokenize(product.occasions)


def occasion_matches(product: Product, occasion: Optional[str], activity: Optional[str]) -> bool:
    """Occasion/activity overlap with the product's own "Occasions / Use" column."""
    tokens = _product_occasion_tokens(product)
    if occasion:
        canon = normalize_occasion(occasion)
        if canon:
            wanted: set[str] = set()
            for word in canon.split(", "):
                wanted |= _OCCASION_EXPAND.get(word, {word})
            if not (wanted & tokens):
                return False
    if activity:
        canon_act = normalize_activity(activity)
        if canon_act:
            wanted_a: set[str] = set()
            for word in canon_act.split():
                wanted_a |= _ACTIVITY_EXPAND.get(word, {word})
            type_tokens = _tokenize(product.product_type) if product.category == "Footwear" else set()
            if not (wanted_a & (tokens | type_tokens)):
                return False
    return True


def _type_blob(product: Product) -> str:
    return (product.product_type + " " + product.product_name).lower()


def footwear_family(product: Product) -> Optional[str]:
    """Closed shoes, sports shoes, flats and sandals stay in separate families."""
    if product.category != "Footwear":
        return None
    blob = _type_blob(product)
    if any(marker in blob for marker in ("sandal", "chappal")) or re.search(r"\bheels?\b", blob):
        return "sandals"
    if any(marker in blob for marker in ("flat", "ballet")):
        return "flats"
    if any(marker in blob for marker in ("running", "training", "sports shoe", "sport shoe", "trail", "walking")):
        return "sports shoes"
    if any(marker in blob for marker in ("sneaker", "casual shoe")):
        return "sneakers"
    return "shoes"


def category_matches(product: Product, category: Optional[str], product_type: Optional[str]) -> bool:
    cat = canonical_category(category)
    if cat and product.category != cat:
        # "Accessories" is also used for "jewellery and accessories" requests
        if not (cat == "Accessories" and product.category == "Jewellery" and not product_type):
            return False
    if product_type:
        canon = canonical_product_type(product_type)
        blob = _type_blob(product)
        if canon:
            aliases = TYPE_ALIASES[canon][0]
            family = footwear_family(product)
            if canon == "shoes":
                return family in {"shoes", "sneakers", "sports shoes"}
            if canon == "sneakers":
                return family == "sneakers"
            if canon == "sports shoes":
                return family == "sports shoes"
            if canon == "flats":
                return family == "flats"
            if canon == "sandals":
                return family == "sandals"
            if canon == "shirt":
                return "shirt" in blob and "dress" not in blob and "t-shirt" not in blob and "tee" not in blob
            if canon == "tshirt":
                return any(token in blob for token in ("t-shirt", "tee"))
            if canon == "trousers":
                return any(token in blob for token in ("trousers", "pants")) and "culotte" not in blob
            if canon == "jewellery":
                return product.category == "Jewellery"
            if not any(alias in blob for alias in aliases):
                return False
        else:
            raw = str(product_type).strip().lower()
            generic = canonical_product_type(raw) is None and raw in {
                "outfit", "outfits", "clothing", "clothes", "apparel", "wear", "casual outfits", "office wear",
            }
            if raw and not generic and raw not in blob and raw not in product.category.lower():
                return False
    return True


_COLOUR_SYNONYMS = {"gray": "grey", "burgundy": "wine", "cream": "ivory", "offwhite": "ivory", "violet": "lavender"}


def colour_matches(product: Product, colour: Optional[str]) -> bool:
    """Match any of the requested colour terms ("peach, pastel") against the product's colour."""
    terms = normalize_colour(colour)
    if not terms:
        return True
    pc = product.colour.lower()
    ptokens = _tokenize(pc)
    for term in terms.split(", "):
        term = _COLOUR_SYNONYMS.get(term, term)
        if " " in term:
            if term in pc:
                return True
        elif term in ptokens:
            return True
    return False


def activity_footwear_constraint(product: Product, activity: Optional[str], priority: Optional[str]) -> bool:
    if product.category != "Footwear" or not activity:
        return True
    canon = normalize_activity(activity)
    if not canon:
        return True
    words = canon.split()
    occ = product.occasions.lower()
    ptype = product.product_type.lower()
    pri = (priority or "").lower()

    def runs() -> bool:
        return "running" in occ or "running" in ptype

    def gyms() -> bool:
        return "gym" in occ or "training" in ptype or "training" in occ

    if "running" in words and "gym" in words:
        if pri == "running":
            return runs()
        if pri == "gym":
            return gyms()
        return runs() or gyms()
    if pri == "running" and "running" in words:
        return runs()
    if pri == "gym" and "gym" in words:
        return gyms()
    if "running" in words:
        return runs()
    if "gym" in words:
        return gyms()
    if "sports" in words:
        return runs() or gyms() or "sports" in occ
    if "walking" in words:
        return "walking" in occ or "walking" in ptype
    return True


_ACCESSORY_TYPES = {"jewellery", "necklace", "earrings", "bracelet", "bangles", "watch", "bag", "clutch"}


_FOOTWEAR_TYPES = {"sports shoes", "sandals", "flats", "sneakers", "casual shoes", "shoes", "heels", "running shoes", "walking shoes"}


def _wants_accessories_now(slots: ShopperSlots, include_accessories: bool) -> bool:
    if include_accessories:
        return True
    category = canonical_category(slots.category)
    if category in {"Jewellery", "Accessories"}:
        return True
    if canonical_product_type(slots.product_type) in _ACCESSORY_TYPES:
        return True
    return bool(slots.metal or slots.look)


def filter_products(products: list[Product], slots: ShopperSlots, include_accessories: bool = False) -> list[Product]:
    result: list[Product] = []
    include_acc = _wants_accessories_now(slots, include_accessories)
    cat = canonical_category(slots.category)
    ptype = canonical_product_type(slots.product_type)
    # a plain "outfit" request is about clothes; footwear only when asked for (or an activity is given)
    clothing_only = not include_acc and (
        (slots.scope == "clothing" and cat != "Footwear" and ptype not in _FOOTWEAR_TYPES)
        or (not cat and not ptype and not slots.activity)
    )
    avoid = set(slots.avoid_ids or [])
    for p in products:
        if p.product_id in avoid:
            continue
        if not include_acc and p.category in ("Jewellery", "Accessories"):
            continue
        if clothing_only and p.category == "Footwear":
            continue
        if not budget_matches(p, slots.budget_max):
            continue
        if not size_matches(p, slots.size):
            continue
        if not occasion_matches(p, slots.occasion, slots.activity):
            continue
        if not category_matches(p, slots.category, slots.product_type):
            continue
        if not colour_matches(p, slots.colour):
            continue
        if not activity_footwear_constraint(p, slots.activity, slots.outfit_priority):
            continue
        result.append(p)
    return result


def _occasion_score(product: Product, occasion: Optional[str]) -> int:
    canon = normalize_occasion(occasion) if occasion else None
    if not canon:
        return 0
    tokens = _product_occasion_tokens(product)
    return sum(1 for word in canon.split(", ") if _OCCASION_EXPAND.get(word, {word}) & tokens)


def rank_products(
    products: list[Product],
    slots: ShopperSlots,
    limit: int = 3,
    diverse: bool = False,
    prefer_higher_price: bool = False,
) -> list[Product]:
    def score(p: Product) -> int:
        s = 3 * _occasion_score(p, slots.occasion)
        if slots.activity:
            canon = normalize_activity(slots.activity)
            if canon:
                words = set()
                for w in canon.split():
                    words |= _ACTIVITY_EXPAND.get(w, {w})
                if words & _product_occasion_tokens(p):
                    s += 2
        if slots.colour and colour_matches(p, slots.colour):
            s += 2
        if slots.style:
            if any(t in p.style_tags.lower() for t in _tokenize(slots.style)):
                s += 4
            else:
                shown = {item.get("product_id") for item in (slots.last_products or [])}
                if p.product_id in shown:
                    s -= 3
        if p.stock_status.lower() == "in stock":
            s += 1
        return s

    sign = -1 if prefer_higher_price else 1
    ranked = sorted(products, key=lambda p: (-score(p), sign * p.price_inr, p.product_id))
    if not diverse:
        return ranked[:limit]
    # spread the picks over different product types (earrings / necklace / bracelet...) before repeating one
    picked: list[Product] = []
    seen: set[str] = set()
    for p in ranked:
        if p.product_type not in seen:
            picked.append(p)
            seen.add(p.product_type)
        if len(picked) == limit:
            return picked
    for p in ranked:
        if p not in picked:
            picked.append(p)
        if len(picked) == limit:
            break
    return picked


def explain_match(product: Product, slots: ShopperSlots) -> str:
    """Reasons built only from catalogue fields and the shopper's stated preferences."""
    reasons: list[str] = []
    if product.stock_status.lower() == "low stock":
        reasons.append("it is listed as Low stock")
    if slots.budget_max is not None and product.price_inr <= slots.budget_max:
        reasons.append(f"it is under your ₹{slots.budget_max} budget")
    if slots.occasion and normalize_occasion(slots.occasion) and occasion_matches(product, slots.occasion, None):
        reasons.append(f"it is listed for {slots.occasion}")
    if slots.activity and normalize_activity(slots.activity) and occasion_matches(product, None, slots.activity):
        reasons.append(f"it is tagged for {slots.activity.strip()}")
    if slots.size and parse_sizes(slots.size):
        listed = listed_sizes_for(product, slots.size)
        if listed:
            reasons.append(f"size {', '.join(listed)} is listed")
        elif size_matches(product, slots.size):
            reasons.append(f"it is available as {product.sizes_raw}")
    if slots.colour and normalize_colour(slots.colour) and colour_matches(product, slots.colour):
        reasons.append(f"the listed colour is {product.colour}")
    if slots.style and any(t in product.style_tags.lower() for t in _tokenize(slots.style)):
        reasons.append(f"the style tags include {slots.style}")
    if (
        slots.product_type
        and canonical_product_type(slots.product_type) not in (None, "jewellery", "shoes", "dress")
        and category_matches(product, slots.category, slots.product_type)
    ):
        reasons.append(f"it matches {slots.product_type}")
    feature = (product.key_features or "").split(";")[0].strip()
    if feature:
        reasons.append(f"the catalogue lists {feature}")
    reasons = reasons[:4]
    if not reasons:
        return "Recommended because it is in the catalogue and passed your filters."
    if len(reasons) == 1:
        return f"Recommended because {reasons[0]}."
    return "Recommended because " + ", ".join(reasons[:-1]) + f", and {reasons[-1]}."


def _clone_slots(slots: ShopperSlots, **kwargs) -> ShopperSlots:
    return replace(slots, **kwargs)


def diagnose_no_match(products: list[Product], slots: ShopperSlots) -> str:
    """Which single constraint, if relaxed, would give results. Colour is checked first (the softest
    preference), then size, budget, and finally occasion/activity. "conflict" means the occasion and
    the activity are each satisfiable alone but not together (e.g. festive + gym)."""
    if slots.colour and filter_products(products, _clone_slots(slots, colour=None)):
        return "colour"
    if slots.size is not None and filter_products(products, _clone_slots(slots, size=None)):
        return "size"
    if slots.budget_max is not None and filter_products(products, _clone_slots(slots, budget_max=None)):
        return "budget"
    no_occ = bool(slots.occasion) and bool(filter_products(products, _clone_slots(slots, occasion=None)))
    no_act = bool(slots.activity) and bool(filter_products(products, _clone_slots(slots, activity=None, outfit_priority=None)))
    if slots.occasion and slots.activity and (no_occ or no_act):
        return "conflict"
    if no_act:
        return "activity"
    if no_occ:
        return "occasion"
    return "requirements"


def accessory_products(products: list[Product], slots: ShopperSlots) -> list[Product]:
    """Up to two jewellery pieces plus one bag/clutch that suit the shortlist's occasion and budget.

    The outfit's own colour/size/activity are not applied (jewellery is one-size or adjustable).
    """
    acc = [p for p in products if p.category in ("Jewellery", "Accessories")]
    base = replace(
        slots,
        category=None,
        product_type=None,
        colour=None,
        activity=None,
        size=None,
        avoid_ids=[],
    )
    matches = filter_products(acc, base, include_accessories=True)
    if not matches and base.occasion:
        matches = filter_products(acc, replace(base, occasion=None), include_accessories=True)
    jewellery = rank_products([p for p in matches if p.category == "Jewellery"], base, limit=2)
    dressy = {"wedding", "party", "cocktail", "festive", "dinner"}
    occ_words = set((normalize_occasion(slots.occasion) or "").split(", "))
    want_type = "clutch" if occ_words & dressy else "tote"
    bags = [p for p in matches if p.category == "Accessories" and want_type in p.product_type.lower()]
    if not bags and not (occ_words & dressy):
        bags = [p for p in matches if p.category == "Accessories" and "watch" not in p.product_type.lower()]
    return jewellery + rank_products(bags, base, limit=1)
