"""Canonicalisers for slot values.

The LLM (and the rule-based NLU) return free text such as ``category="clothing"``,
``occasion="birthday"``, ``size="M or L"`` or ``colour="Peach or pastel shades"``.
The catalogue filters need a small closed vocabulary, so every slot value is
normalised here before it is stored.  Python 3.9 compatible.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

CANON_CATEGORIES = ("Ethnic wear", "Western wear", "Jewellery", "Accessories", "Footwear")

# --------------------------------------------------------------------------- sizes
_SIZE_WORDS = {
    "XSMALL": "XS",
    "EXTRASMALL": "XS",
    "SMALL": "S",
    "MEDIUM": "M",
    "LARGE": "L",
    "XLARGE": "XL",
    "EXTRALARGE": "XL",
}
_CLOTHING_RE = re.compile(r"(?<![A-Za-z0-9'])(XXXL|XXL|XXS|XL|XS|S|M|L|X-LARGE|EXTRA[ -]?LARGE|EXTRA[ -]?SMALL|X-SMALL|SMALL|MEDIUM|LARGE)(?![A-Za-z0-9'])", re.I)


def parse_sizes(value) -> List[str]:
    """Return the list of canonical sizes mentioned in ``value``.

    ``"M or L"`` -> ``["M", "L"]``; ``"UK 6"`` -> ``["UK 6"]``; ``"2.6"`` -> ``["2.6"]``.
    Free/one size words return an empty list.
    """
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    upper = text.upper()
    if "UK" in upper:
        # "UK 6", "UK 6 or 7", "UK6, UK7"
        rest = upper[upper.index("UK"):]
        nums = re.findall(r"\d+(?:\.\d+)?", rest)
        out: List[str] = []
        for n in nums:
            token = "UK " + (n[:-2] if n.endswith(".0") else n)
            if token not in out:
                out.append(token)
        return out
    decimals = re.findall(r"(?<![\d.])2\.[0-9](?![\d.])", text)
    if decimals:
        out = []
        for d in decimals:
            if d not in out:
                out.append(d)
        return out
    out = []
    for match in _CLOTHING_RE.finditer(text):
        token = re.sub(r"[\s-]", "", match.group(1).upper())
        token = _SIZE_WORDS.get(token, token)
        if token not in out:
            out.append(token)
    return out


def format_sizes(sizes: Iterable[str]) -> Optional[str]:
    sizes = list(sizes)
    if not sizes:
        return None
    return ", ".join(sizes)


def normalize_size(value) -> Optional[str]:
    return format_sizes(parse_sizes(value))


def size_kind(size: str) -> str:
    if size.upper().startswith("UK"):
        return "shoe"
    if re.fullmatch(r"\d\.\d", size):
        return "bangle"
    return "clothing"


# --------------------------------------------------------------------------- category / type
_CATEGORY_MAP = {
    "ethnic": "Ethnic wear",
    "ethnic wear": "Ethnic wear",
    "ethnicwear": "Ethnic wear",
    "indian": "Ethnic wear",
    "indian wear": "Ethnic wear",
    "traditional": "Ethnic wear",
    "traditional wear": "Ethnic wear",
    "western": "Western wear",
    "western wear": "Western wear",
    "westernwear": "Western wear",
    "jewellery": "Jewellery",
    "jewelry": "Jewellery",
    "jewelery": "Jewellery",
    "jewels": "Jewellery",
    "accessories": "Accessories",
    "accessory": "Accessories",
    "footwear": "Footwear",
    "shoes": "Footwear",
    "shoe": "Footwear",
    "sandals": "Footwear",
    "sneakers": "Footwear",
    "flats": "Footwear",
}

# canonical product type -> (substrings searched in "product type + name", default category)
TYPE_ALIASES = {
    "dress": (["dress", "jumpsuit", "anarkali", "lehenga", "saree", "kurta", "suit", "co-ord", "coord", "sharara"], None),
    "lehenga": (["lehenga"], "Ethnic wear"),
    "saree": (["saree"], "Ethnic wear"),
    "kurta": (["kurta"], "Ethnic wear"),
    "anarkali": (["anarkali"], "Ethnic wear"),
    "sharara": (["sharara"], "Ethnic wear"),
    "suit": (["suit", "anarkali", "sharara", "lehenga", "co-ord", "coord"], None),
    "co-ord": (["co-ord", "coord"], "Western wear"),
    "jumpsuit": (["jumpsuit"], "Western wear"),
    "shirt": (["shirt"], "Western wear"),
    "trousers": (["trousers", "pants"], "Western wear"),
    "tshirt": (["t-shirt", "tee"], "Western wear"),
    "activewear": (["activewear", "tights", "gym set"], "Western wear"),
    "culottes": (["culottes"], "Western wear"),
    "shoes": (["shoe", "sneaker", "running", "walking", "trail", "training"], "Footwear"),
    "sports shoes": (["running shoes", "walking shoes", "trail shoes", "training shoes", "sports shoes"], "Footwear"),
    "sneakers": (["sneaker", "casual shoes"], "Footwear"),
    "flats": (["flat"], "Footwear"),
    "sandals": (["sandal"], "Footwear"),
    "jewellery": (["earring", "necklace", "bangle", "bracelet", "jhumka", "choker", "cuff"], "Jewellery"),
    "necklace": (["necklace", "choker", "chain"], "Jewellery"),
    "earrings": (["earring", "jhumka"], "Jewellery"),
    "bracelet": (["bracelet", "cuff"], "Jewellery"),
    "bangles": (["bangle"], "Jewellery"),
    "watch": (["watch"], "Accessories"),
    "bag": (["tote", "clutch", "bag"], "Accessories"),
    "clutch": (["clutch"], "Accessories"),
}

_TYPE_SYNONYMS = [
    (r"\b(dress(es)?|gowns?|frocks?)\b", "dress"),
    (r"\blehengas?\b", "lehenga"),
    (r"\b(sarees?|saris?)\b", "saree"),
    (r"\b(kurtas?|kurtis?)\b", "kurta"),
    (r"\banarkalis?\b", "anarkali"),
    (r"\bshararas?\b", "sharara"),
    (r"\bjumpsuits?\b", "jumpsuit"),
    (r"\bco[- ]?ords?\b", "co-ord"),
    (r"\b(t[- ]?shirts?|tees?)\b", "tshirt"),
    (r"\bshirts?\b", "shirt"),
    (r"\b(trousers?|pants)\b", "trousers"),
    (r"\bculottes?\b", "culottes"),
    (r"\b(tights|leggings|activewear|gym set|gym wear|sportswear)\b", "activewear"),
    (r"\b(sports shoes?|running shoes?|training shoes?|trainers?|trail shoes?|walking shoes?)\b", "sports shoes"),
    (r"\b(sneakers?|casual shoes?|kicks)\b", "sneakers"),
    (r"\b(flats?|ballet flats?|ballerinas?|pointed flats)\b", "flats"),
    (r"\b(sandals?|chappals?|heels?|heeled sandals?)\b", "sandals"),
    (r"\b(shoes?|footwear)\b", "shoes"),
    (r"\b(necklaces?|chains?|chokers?|pendants?)\b", "necklace"),
    (r"\b(earrings?|jhumkas?|jhumkis?|studs?|hoops?)\b", "earrings"),
    (r"\bbangles?\b", "bangles"),
    (r"\b(bracelets?|cuffs?)\b", "bracelet"),
    (r"\b(jewell?ery|jewelry|jewels)\b", "jewellery"),
    (r"\bwatch(es)?\b", "watch"),
    (r"\bclutch(es)?\b", "clutch"),
    (r"\b(bags?|totes?|purses?|handbags?)\b", "bag"),
]

# Whole-outfit requests: no category / type restriction (but clothing only).
_GENERIC_OUTFIT = re.compile(
    r"^(outfits?|clothes|clothing|apparel|wear|attire|looks?|office wear|casual wear|daily wear|party wear|"
    r"occasion ?wear|formal wear|casuals?|ethnics?|western)$",
    re.I,
)


def canonical_product_type(value) -> Optional[str]:
    """Map free text to a canonical product type key, or None if generic/unknown.

    When several product words appear ("jewellery for my peach dress") the one mentioned first wins,
    because the thing being asked for normally comes before the outfit it goes with.
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or _GENERIC_OUTFIT.match(text):
        return None
    best = None
    best_pos = None
    for pattern, canon in _TYPE_SYNONYMS:
        m = re.search(pattern, text)
        if m and (best_pos is None or m.start() < best_pos):
            best, best_pos = canon, m.start()
    return best


CLOTHING_TYPES = {
    "dress", "lehenga", "saree", "kurta", "anarkali", "sharara", "jumpsuit", "co-ord", "tshirt", "shirt",
    "trousers", "culottes", "activewear", "suit",
}
_OWNED_OUTFIT = re.compile(
    r"\b(i have|i got|i own|i am wearing|i'm wearing|im wearing|wearing|my|this|that|already have)\b[^.?!]{0,30}$"
)


def product_types_in(text: str) -> List[str]:
    """All canonical product types mentioned in ``text`` in order of appearance."""
    text = text.lower()
    found = []
    for pattern, canon in _TYPE_SYNONYMS:
        for m in re.finditer(pattern, text):
            found.append((m.start(), canon, text[: m.start()]))
    found.sort()
    out = []
    for _, canon, before in found:
        if canon not in [c for c, _b in out]:
            out.append((canon, before))
    return out


def requested_product_type(text: str) -> Optional[str]:
    """The product the shopper is asking for.

    "I have a peach dress. What jewellery would look good with it?" asks for jewellery: a clothing
    noun that follows "I have / my / wearing" describes what the shopper already owns.
    """
    found = product_types_in(text)
    if not found:
        return None
    wanted = [c for c, before in found if not (c in CLOTHING_TYPES and _OWNED_OUTFIT.search(before))]
    others = [c for c in wanted if c not in CLOTHING_TYPES]
    if len(wanted) != len(found) and others:
        return others[0]
    if len(found) > 1 and any(c in CLOTHING_TYPES for c, _ in found) and any(c not in CLOTHING_TYPES for c, _ in found):
        # "jewellery for my dress" -> jewellery; "dress for ... sandals" -> dress (first mention)
        return found[0][0]
    return found[0][0]


def canonical_category(value) -> Optional[str]:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).strip().lower())
    if not text:
        return None
    if text in _CATEGORY_MAP:
        return _CATEGORY_MAP[text]
    for canon in CANON_CATEGORIES:
        if text == canon.lower():
            return canon
    return None


def category_for_type(product_type: Optional[str]) -> Optional[str]:
    if not product_type:
        return None
    entry = TYPE_ALIASES.get(product_type)
    return entry[1] if entry else None


def normalize_category_and_type(category, product_type):
    """Return ``(category, product_type)`` using only canonical values."""
    ptype = canonical_product_type(product_type)
    cat = canonical_category(category)
    if cat is None and category is not None:
        # the LLM sometimes puts a type in the category field ("lehenga", "sandals")
        as_type = canonical_product_type(category)
        if as_type and ptype is None:
            ptype = as_type
    if cat is None and ptype:
        cat = category_for_type(ptype)
    if cat and ptype and category_for_type(ptype) and category_for_type(ptype) != cat:
        # contradictory (e.g. category Jewellery, type "dress") - trust the type
        cat = category_for_type(ptype)
    return cat, ptype


# --------------------------------------------------------------------------- occasions
OCCASION_CANON = [
    ("wedding", r"\b(wedding|weddings|shaadi|shadi|marriage|reception|sangeet|mehendi|mehndi|engagement)\b"),
    ("cocktail", r"\bcocktail\b"),
    ("festive", r"\b(festive|festival|diwali|pooja|puja|navratri|eid|karva|holi|raksha)\b"),
    ("party", r"\b(party|partywear|night ?out|club(bing)?)\b"),
    ("office", r"\b(office|workwear|work wear|corporate|9 ?to ?5|work|formals)\b"),
    ("daily", r"\b(daily|day to day)\b"),
    ("casual", r"\b(casual|casuals|everyday|day out)\b"),
    ("brunch", r"\b(brunch|day event|daytime|day function|lunch)\b"),
    ("dinner", r"\b(dinner|date night)\b"),
    ("travel", r"\b(travel|holiday|vacation|trip)\b"),
    ("college", r"\bcollege\b"),
    ("gym", r"\b(gym|workout|exercise|training)\b"),
    ("running", r"\b(running|run|jogging)\b"),
    ("sports", r"\bsports?\b"),
]
GIFT_WORDS = re.compile(r"\b(birthday|gift|gifting|anniversary|present|surprise)\b", re.I)


def normalize_occasion(value) -> Optional[str]:
    """Canonical occasion words joined by ', ' ("office and daily wear" -> "office, daily").

    Gift occasions (birthday, anniversary...) are not a product occasion and return None.
    Activities (running / gym / sports) are handled by the activity slot.
    """
    if value is None:
        return None
    text = str(value).lower()
    found: List[str] = []
    for canon, pattern in OCCASION_CANON:
        if canon in ("gym", "running", "sports"):
            continue
        if re.search(pattern, text) and canon not in found:
            found.append(canon)
    if "wedding" in found and "party" in found and "wedding" in text:
        # "wedding party" is still a wedding
        found.remove("party")
    return ", ".join(found) if found else None


def normalize_activity(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).lower()
    found: List[str] = []
    if re.search(r"\b(running|run|jogging|marathon)\b", text):
        found.append("running")
    if re.search(r"\b(gym|workout|exercise|training|crossfit)\b", text):
        found.append("gym")
    if not found and re.search(r"\b(sports?|sporty|athletic)\b", text):
        found.append("sports")
    if not found and re.search(r"\b(walk|walking)\b", text):
        found.append("walking")
    if not found and re.search(r"\b(trail|hiking|trek)\b", text):
        found.append("trail")
    return " ".join(found) if found else None


# --------------------------------------------------------------------------- colours / style
COLOUR_STOPWORDS = {
    "or", "and", "any", "shade", "shades", "colour", "colours", "color", "colors", "tone", "tones",
    "light", "dark", "bright", "deep", "soft", "the", "a", "an", "in", "of", "with", "like", "preferably",
    "something", "colored", "coloured", "ish", "no", "preference", "none", "skip",
}
SKIN_TONE_WORDS = {"dusky", "fair", "wheatish", "dark", "tan", "tanned", "olive", "brown", "medium", "deep", "light", "dusky-skinned"}
STYLE_WORDS = {
    "minimal": "minimal",
    "minimalist": "minimal",
    "subtle": "minimal",
    "simple": "minimal",
    "traditional": "traditional",
    "classic": "classic",
    "elegant": "elegant",
    "statement": "statement",
    "contemporary": "contemporary",
    "modern": "modern",
    "sporty": "sporty",
    "floral": "floral",
    "casual": "casual",
    "comfortable": "comfortable",
    "comfort": "comfortable",
    "playful": "playful",
}


def normalize_colour(value) -> Optional[str]:
    """"Peach or pastel shades" -> "peach, pastel"."""
    if value is None:
        return None
    text = str(value).lower().replace("&", " and ")
    text = re.sub(r"[^a-z\- ,/]", " ", text)
    text = re.sub(r"\brose[- ]gold\b", "rosegold", text)
    parts = [w for w in re.split(r"[\s,/]+", text) if w and w not in COLOUR_STOPWORDS]
    parts = ["rose gold" if p == "rosegold" else p for p in parts]
    out: List[str] = []
    for p in parts:
        if p not in out:
            out.append(p)
    return ", ".join(out) if out else None


def normalize_style(value) -> Optional[str]:
    """Keep only recognised style words; skin tones and filler (stylish, dusky) are dropped."""
    if value is None:
        return None
    text = str(value).lower()
    found: List[str] = []
    for word in re.findall(r"[a-z]+", text):
        canon = STYLE_WORDS.get(word)
        if canon and canon not in found:
            found.append(canon)
    return ", ".join(found) if found else None


_STOP_FOR_FOLD = re.compile(r"\s+")


def clean_text(value, limit: int = 60) -> Optional[str]:
    if value is None:
        return None
    text = _STOP_FOR_FOLD.sub(" ", str(value)).strip()
    return text[:limit] if text else None
