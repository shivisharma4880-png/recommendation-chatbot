"""Catalogue-faithful dummy product images: unique silhouettes from type, colour and features."""

from __future__ import annotations

from typing import Tuple

from src.catalogue import Product

CATEGORY_EMOJI = {
    "Ethnic wear": "👗",
    "Western wear": "👚",
    "Jewellery": "💍",
    "Accessories": "👜",
    "Footwear": "👟",
}

COLOUR_HEX = {
    "peach": "#e8b4a2",
    "black": "#1c1c1c",
    "white": "#f4f1ee",
    "teal": "#3d7a78",
    "mustard": "#c4a035",
    "cream": "#f3ead8",
    "red": "#b33a3a",
    "yellow": "#d4b24a",
    "blush": "#d9a5b3",
    "navy": "#24344d",
    "blue": "#4d6d9a",
    "green": "#3f6b4e",
    "emerald": "#2f6b57",
    "maroon": "#7a2e3a",
    "gold": "#c6a15b",
    "silver": "#b8b8b8",
    "rose gold": "#c9837a",
    "rose": "#c9837a",
    "beige": "#d7c4a8",
    "tan": "#c4a574",
    "ivory": "#f3ead8",
    "lavender": "#c5b4d3",
    "olive": "#6b6f43",
    "coral": "#d76a6a",
    "nude": "#e0c3b0",
    "champagne": "#e6d3b3",
    "wine": "#6e2c3a",
    "rust": "#b85c38",
    "grey": "#8a8580",
    "gray": "#8a8580",
    "pink": "#d9a5b3",
    "lilac": "#c5b4d3",
    "mint": "#9dcdc0",
    "sage": "#9aaa8c",
    "charcoal": "#3a3a3a",
    "indigo": "#3d4c7a",
    "mauve": "#b08a9a",
    "antique": "#c6a15b",
    "pearl": "#efe8dc",
    "pastel": "#e8c4d0",
    "neon": "#b6e05a",
    "multicolour": "#c9837a",
}


def colour_hex(colour: str) -> str:
    lower = (colour or "").lower()
    best = None
    best_len = 0
    for name, hex_code in COLOUR_HEX.items():
        if name in lower and len(name) > best_len:
            best = hex_code
            best_len = len(name)
    return best or "#a18a76"


def category_emoji(category: str) -> str:
    return CATEGORY_EMOJI.get(category, "🛍️")


def static_image_path(product_id: str) -> str:
    return f"/static/product-images/{product_id}.jpg"


def visual_for(product: Product) -> dict:
    image_url = getattr(product, "image_url", "") or static_image_path(product.product_id)
    if image_url and "?" not in image_url:
        image_url = f"{image_url}?v=7"
    return {
        "emoji": category_emoji(product.category),
        "accent_color": colour_hex(product.colour),
        "image_url": image_url,
    }


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _seed(product: Product) -> int:
    return sum((i + 1) * ord(ch) for i, ch in enumerate(product.product_id or "X"))


def _shade(hex_code: str, amount: int) -> str:
    hex_code = (hex_code or "#a18a76").lstrip("#")
    rgb = [int(hex_code[i : i + 2], 16) for i in (0, 2, 4)]
    rgb = [max(0, min(255, c + amount)) for c in rgb]
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _ink_for(fill: str) -> str:
    return (
        "#f7f4f1"
        if fill in {"#1c1c1c", "#24344d", "#3a3a3a", "#3d4c7a", "#2f6b57", "#7a2e3a", "#6e2c3a"}
        else "#1c1c1c"
    )


def _kind(product: Product) -> str:
    text = f"{product.product_type} {product.product_name} {product.key_features}".lower()
    mapping = (
        ("jhumka", "jhumka"),
        ("drop earring", "drop"),
        ("hoop", "hoop"),
        ("stud", "stud"),
        ("choker", "choker"),
        ("necklace set", "choker"),
        ("necklace", "necklace"),
        ("bangle", "bangles"),
        ("cuff", "cuff"),
        ("bracelet", "bracelet"),
        ("watch", "watch"),
        ("clutch", "clutch"),
        ("tote", "tote"),
        ("lehenga", "lehenga"),
        ("saree", "saree"),
        ("anarkali", "anarkali"),
        ("sharara", "sharara"),
        ("straight suit", "suit"),
        ("kurta set", "kurta_set"),
        ("kurta", "kurta"),
        ("jumpsuit", "jumpsuit"),
        ("co-ord", "coord"),
        ("shirt dress", "shirt_dress"),
        ("maxi", "maxi"),
        ("midi", "midi"),
        ("activewear", "active"),
        ("tights", "tights"),
        ("culotte", "culottes"),
        ("trouser", "trousers"),
        ("t-shirt", "tee"),
        ("shirt", "shirt"),
        ("ballet", "ballet"),
        ("pointed", "pointed_flat"),
        ("heeled sandal", "heel"),
        ("sandal", "sandal"),
        ("trail", "trail"),
        ("running", "runner"),
        ("walking", "walker"),
        ("training", "trainer"),
        ("sports shoe", "sport"),
        ("sneaker", "sneaker"),
        ("casual shoe", "casual_shoe"),
        ("flats", "flat"),
    )
    for needle, kind in mapping:
        if needle in text:
            return kind
    if product.category == "Footwear":
        return "sneaker"
    if product.category == "Jewellery":
        return "necklace"
    if product.category == "Accessories":
        return "tote"
    if product.category == "Ethnic wear":
        return "kurta"
    return "midi"


def _pattern(product: Product, fill: str, seed: int) -> str:
    blob = f"{product.key_features} {product.style_tags} {product.colour} {product.material}".lower()
    dots = []
    if "floral" in blob:
        for i in range(6):
            x = 70 + (i * 50 + seed * 3) % 260
            y = 80 + (i * 41 + seed) % 220
            dots.append(f'<circle cx="{x}" cy="{y}" r="8" fill="{_shade(fill, 40)}" opacity="0.4"/>')
    elif "embroider" in blob or "embellish" in blob or "kundan" in blob:
        for i in range(5):
            x = 90 + (i * 55 + seed) % 220
            y = 90 + (i * 39) % 200
            dots.append(
                f'<rect x="{x}" y="{y}" width="10" height="10" fill="{_shade(fill, 50)}" transform="rotate(45 {x+5} {y+5})" opacity="0.5"/>'
            )
    elif "mesh" in blob:
        for i in range(10):
            x = 70 + (i % 5) * 55
            y = 90 + (i // 5) * 80
            dots.append(f'<circle cx="{x + seed % 11}" cy="{y}" r="4" fill="#fff" opacity="0.35"/>')
    elif "pearl" in blob:
        for i in range(5):
            x = 110 + i * 45
            dots.append(f'<circle cx="{x}" cy="{100 + (i % 2) * 18}" r="7" fill="#efe8dc" stroke="{fill}" stroke-width="2"/>')
    return "".join(dots)


def _sheen(product: Product) -> str:
    if product.category == "Jewellery":
        return ""
    blob = f"{product.material} {product.style_tags} {product.key_features}".lower()
    if any(word in blob for word in ("satin", "silk", "tissue", "gold", "plated", "sheen")):
        return '<rect x="55" y="50" width="55" height="300" fill="#ffffff" opacity="0.16"/>'
    return ""


def _metal_hex(product: Product, fill: str) -> str:
    colour = (product.colour or "").lower()
    if "rose gold" in colour:
        return "#c9837a"
    if "silver" in colour:
        return "#c0c4c8"
    if "antique" in colour:
        return "#b08a3c"
    if "gold" in colour:
        return "#c6a15b"
    if "pearl" in colour:
        return "#d9c7a0"
    return fill


def _quad_point(t: float, x0: float, y0: float, cx: float, cy: float, x1: float, y1: float) -> Tuple[float, float]:
    mt = 1 - t
    return (
        mt * mt * x0 + 2 * mt * t * cx + t * t * x1,
        mt * mt * y0 + 2 * mt * t * cy + t * t * y1,
    )


def _chain_path(x0: int, y0: int, cx: int, cy: int, x1: int, y1: int, metal: str, width: int) -> str:
    return f'<path d="M{x0} {y0} Q{cx} {cy} {x1} {y1}" fill="none" stroke="{metal}" stroke-width="{width}"/>'


def _necklace_body(product: Product, fill: str, metal: str, seed: int) -> str:
    blob = f"{product.product_id} {product.product_name} {product.key_features} {product.style_tags}".lower()
    x0, y0, cx, cy, x1, y1 = 88, 86, 200, 360, 312, 86
    bx, by = _quad_point(0.5, x0, y0, cx, cy, x1, y1)
    clasp = (
        f'<circle cx="{x0}" cy="{y0}" r="8" fill="{metal}"/>'
        f'<circle cx="{x1}" cy="{y0}" r="8" fill="{metal}"/>'
    )
    chain = _chain_path(x0, y0, cx, cy, x1, y1, metal, 6)
    if "pearl" in blob or "collar" in blob:
        beads = []
        for i in range(15):
            t = i / 14
            px, py = _quad_point(t, x0, y0, cx, cy, x1, y1)
            radius = 8 if i in (0, 14) else 12
            beads.append(
                f'<circle cx="{px:.0f}" cy="{py:.0f}" r="{radius}" fill="#efe8dc" stroke="{metal}" stroke-width="3"/>'
            )
        return clasp + "".join(beads)
    if "layered" in blob or "coin" in blob:
        coins = []
        for i, t in enumerate((0.35, 0.5, 0.65)):
            px, py = _quad_point(t, 100, 110, 200, 380, 300, 110)
            coins.append(
                f'<circle cx="{px:.0f}" cy="{py + 18:.0f}" r="18" fill="{metal}"/>'
                f'<circle cx="{px:.0f}" cy="{py + 18:.0f}" r="7" fill="#efe8dc"/>'
            )
        return (
            clasp
            + _chain_path(92, 90, 200, 280, 308, 90, metal, 5)
            + _chain_path(100, 100, 200, 330, 300, 100, metal, 5)
            + _chain_path(108, 110, 200, 380, 292, 110, metal, 6)
            + "".join(coins)
        )
    if "bar" in blob:
        return (
            clasp
            + chain
            + f'<rect x="{bx - 42:.0f}" y="{by + 2:.0f}" width="84" height="10" rx="4" fill="{metal}"/>'
        )
    if "locket" in blob:
        return (
            clasp
            + chain
            + f'<ellipse cx="{bx:.0f}" cy="{by + 34:.0f}" rx="28" ry="36" fill="{fill}" stroke="{metal}" stroke-width="6"/>'
            + f'<ellipse cx="{bx:.0f}" cy="{by + 34:.0f}" rx="11" ry="15" fill="none" stroke="{metal}" stroke-width="3"/>'
        )
    if "temple" in blob:
        return (
            clasp
            + _chain_path(x0, y0, cx, cy, x1, y1, metal, 8)
            + f'<circle cx="{bx:.0f}" cy="{by + 36:.0f}" r="36" fill="{fill}" stroke="{metal}" stroke-width="6"/>'
            + f'<rect x="{bx - 12:.0f}" y="{by + 24:.0f}" width="24" height="24" fill="#efe8dc" transform="rotate(45 {bx:.0f} {by + 36:.0f})"/>'
        )
    if "cord" in blob or "disc" in blob:
        cord = "#2a2623"
        return (
            _chain_path(x0, y0, cx, cy, x1, y1, cord, 8)
            + f'<circle cx="{bx:.0f}" cy="{by + 32:.0f}" r="32" fill="{metal}"/>'
            + f'<circle cx="{bx:.0f}" cy="{by + 32:.0f}" r="11" fill="#efe8dc"/>'
        )
    if "small pendant" in blob or "minimal" in blob:
        return (
            clasp
            + _chain_path(x0, y0, cx, cy, x1, y1, metal, 4)
            + f'<circle cx="{bx:.0f}" cy="{by + 14:.0f}" r="12" fill="{fill}" stroke="{metal}" stroke-width="4"/>'
        )
    pendants = (
        f'<circle cx="{bx:.0f}" cy="{by + 18:.0f}" r="16" fill="{fill}" stroke="{metal}" stroke-width="5"/>',
        f'<path d="M{bx:.0f} {by + 2:.0f} l16 30 h-32z" fill="{fill}" stroke="{metal}" stroke-width="5"/>',
        f'<rect x="{bx - 14:.0f}" y="{by + 4:.0f}" width="28" height="28" rx="4" fill="{fill}" stroke="{metal}" stroke-width="5"/>',
        f'<ellipse cx="{bx:.0f}" cy="{by + 22:.0f}" rx="14" ry="20" fill="{fill}" stroke="{metal}" stroke-width="5"/>',
    )
    return clasp + chain + pendants[seed % 4]


def _draw(kind: str, fill: str, product: Product, seed: int) -> str:
    dark = _shade(fill, -28)
    light = _shade(fill, 36)
    accent = _shade(fill, -50) if seed % 2 else _shade(fill, 20)
    metal = _metal_hex(product, fill)
    ink = "#2a2623"
    buttons = "".join(f'<circle cx="200" cy="{150 + i * 32}" r="5" fill="{accent}"/>' for i in range(5))
    stones = "".join(f'<circle cx="{110 + i * 36}" cy="148" r="8" fill="{fill}"/>' for i in range(5))
    laces = "".join(f'<line x1="{90 + i * 18}" y1="175" x2="{102 + i * 18}" y2="205" stroke="{light}" stroke-width="4"/>' for i in range(6))
    drawings = {
        "anarkali": f'<circle cx="200" cy="58" r="22" fill="#e8d5c4"/><path d="M158 82 h84 l14 44 H144z" fill="{dark}"/><path d="M88 126 h224 l48 230 H40z" fill="{fill}"/>',
        "lehenga": f'<circle cx="200" cy="52" r="20" fill="#e8d5c4"/><path d="M158 74 h84 l12 48 H146z" fill="{dark}"/><ellipse cx="200" cy="268" rx="168" ry="108" fill="{fill}"/>',
        "saree": f'<circle cx="148" cy="58" r="20" fill="#e8d5c4"/><path d="M118 80 h64 v250 H108z" fill="{fill}"/><path d="M182 96 q110 30 128 210 l-48 48 q-90-50-170-36" fill="{dark}"/><rect x="90" y="338" width="220" height="16" fill="{accent}"/>',
        "kurta": f'<circle cx="200" cy="56" r="20" fill="#e8d5c4"/><path d="M92 88 h216 l24 48 v210 H68 V136z" fill="{fill}"/><path d="M92 136 h-48 v110 h48"/><path d="M308 136 h48 v110 h-48" fill="{dark}"/><line x1="200" y1="108" x2="200" y2="280" stroke="{dark}" stroke-width="3"/>',
        "kurta_set": f'<circle cx="132" cy="58" r="18" fill="#e8d5c4"/><rect x="70" y="80" width="124" height="250" rx="14" fill="{fill}"/><rect x="230" y="140" width="100" height="210" rx="12" fill="{dark}"/><rect x="218" y="118" width="124" height="22" fill="{accent}"/>',
        "suit": f'<circle cx="132" cy="56" r="18" fill="#e8d5c4"/><rect x="72" y="78" width="122" height="250" fill="{fill}"/><rect x="232" y="128" width="96" height="230" fill="{dark}"/><path d="M194 96 q110 16 140 48 v24 H214z" fill="{light}"/>',
        "sharara": f'<circle cx="200" cy="54" r="20" fill="#e8d5c4"/><rect x="148" y="76" width="104" height="110" fill="{dark}"/><path d="M70 186 h260 l60 170 H10z" fill="{fill}"/>',
        "midi": f'<circle cx="200" cy="54" r="20" fill="#e8d5c4"/><path d="M164 76 l36 28 36-28 v44 H164z" fill="{dark}"/><path d="M96 120 h208 l36 230 H60z" fill="{fill}"/>',
        "maxi": f'<circle cx="200" cy="50" r="20" fill="#e8d5c4"/><path d="M166 72 h68 l12 36 H154z" fill="{dark}"/><path d="M70 108 h260 l70 250 H0z" fill="{fill}"/>',
        "shirt_dress": f'<circle cx="200" cy="54" r="20" fill="#e8d5c4"/><path d="M170 76 l30 22 30-22 v36 H170z" fill="{dark}"/><path d="M96 112 h208 v228 H96z" fill="{fill}"/>{buttons}<path d="M96 210 h-36 v56 h36M304 210 h36 v56 h-36" fill="{dark}"/>',
        "shirt": (
            f'<path d="M70 120 L150 88 H250 L330 120 V175 H290 V350 H110 V175 H70 Z" fill="{fill}"/>'
            f'<path d="M150 88 L200 132 L250 88 V140 H150z" fill="{dark}"/>'
            f'<rect x="186" y="150" width="28" height="160" fill="{light}" opacity="0.7"/>'
            f'{buttons}'
        ),
        "tee": f'<path d="M60 130 h90 V108 h100 v22 h90 v220 H60z" fill="{fill}"/><circle cx="86" cy="142" r="8" fill="{dark}"/><circle cx="314" cy="142" r="8" fill="{dark}"/>',
        "jumpsuit": f'<circle cx="200" cy="54" r="20" fill="#e8d5c4"/><rect x="128" y="78" width="144" height="90" fill="{fill}"/><rect x="118" y="168" width="68" height="190" fill="{dark}"/><rect x="214" y="168" width="68" height="190" fill="{dark}"/><rect x="158" y="154" width="84" height="16" fill="{accent}"/>',
        "coord": f'<rect x="40" y="70" width="150" height="110" rx="14" fill="{fill}"/><rect x="62" y="200" width="106" height="160" rx="12" fill="{dark}"/><rect x="220" y="90" width="140" height="270" rx="16" fill="{fill}"/>',
        "trousers": f'<rect x="110" y="48" width="180" height="44" rx="12" fill="{dark}"/><rect x="118" y="92" width="76" height="270" fill="{fill}"/><rect x="206" y="92" width="76" height="270" fill="{_shade(fill, -12)}"/>',
        "culottes": f'<rect x="108" y="56" width="184" height="40" rx="12" fill="{dark}"/><path d="M110 96 h80 l28 260 H82z" fill="{fill}"/><path d="M210 96 h80 l-28 260 H238z" fill="{_shade(fill, -14)}"/>',
        "active": f'<path d="M110 48 h180 l16 64 H94z" fill="{fill}"/><rect x="108" y="112" width="80" height="250" fill="{dark}"/><rect x="212" y="112" width="80" height="250" fill="{dark}"/>',
        "tights": f'<rect x="128" y="40" width="144" height="52" rx="20" fill="{dark}"/><rect x="132" y="92" width="64" height="270" fill="{fill}"/><rect x="204" y="92" width="64" height="270" fill="{_shade(fill, -16)}"/>',
        "jhumka": f'<circle cx="130" cy="80" r="16" fill="{metal}"/><path d="M130 96 l32 110 H98z" fill="{fill}"/><circle cx="130" cy="226" r="28" fill="{metal}"/><circle cx="270" cy="80" r="16" fill="{metal}"/><path d="M270 96 l32 110 H238z" fill="{fill}"/><circle cx="270" cy="226" r="28" fill="{metal}"/>',
        "drop": f'<circle cx="130" cy="80" r="14" fill="{metal}"/><ellipse cx="130" cy="190" rx="28" ry="48" fill="#efe8dc" stroke="{metal}" stroke-width="6"/><circle cx="270" cy="80" r="14" fill="{metal}"/><ellipse cx="270" cy="190" rx="28" ry="48" fill="#efe8dc" stroke="{metal}" stroke-width="6"/>',
        "hoop": f'<circle cx="130" cy="200" r="70" fill="none" stroke="{metal}" stroke-width="16"/><circle cx="270" cy="200" r="70" fill="none" stroke="{metal}" stroke-width="16"/>',
        "stud": f'<circle cx="130" cy="200" r="42" fill="{metal}"/><circle cx="130" cy="200" r="18" fill="#efe8dc"/><circle cx="270" cy="200" r="42" fill="{metal}"/><circle cx="270" cy="200" r="18" fill="#efe8dc"/>',
        "necklace": _necklace_body(product, fill, metal, seed),
        "choker": f'<rect x="70" y="130" width="260" height="28" rx="12" fill="{metal}"/><g>{stones}</g><circle cx="130" cy="230" r="20" fill="{metal}"/><circle cx="270" cy="230" r="20" fill="{metal}"/>',
        "bangles": f'<ellipse cx="160" cy="200" rx="90" ry="42" fill="none" stroke="{metal}" stroke-width="16"/><ellipse cx="240" cy="220" rx="90" ry="42" fill="none" stroke="{fill}" stroke-width="16"/>',
        "bracelet": f'<rect x="50" y="170" width="300" height="48" rx="24" fill="{metal}"/><circle cx="86" cy="194" r="16" fill="{fill}"/><circle cx="314" cy="194" r="16" fill="{fill}"/>',
        "cuff": f'<path d="M70 120 h260 v100 h-54 v-52 H124 v52 H70z" fill="{metal}"/>',
        "watch": f'<rect x="164" y="36" width="72" height="88" rx="12" fill="{dark}"/><circle cx="200" cy="210" r="84" fill="{fill}" stroke="{metal}" stroke-width="16"/><circle cx="200" cy="210" r="12" fill="{metal}"/><line x1="200" y1="210" x2="200" y2="150" stroke="{ink}" stroke-width="8"/><line x1="200" y1="210" x2="248" y2="226" stroke="{ink}" stroke-width="6"/><rect x="164" y="294" width="72" height="88" rx="12" fill="{dark}"/>',
        "clutch": f'<rect x="48" y="140" width="304" height="140" rx="20" fill="{fill}"/><rect x="48" y="140" width="304" height="32" fill="{dark}"/><rect x="176" y="128" width="48" height="20" rx="6" fill="{metal}"/>',
        "tote": f'<path d="M90 90 h48 v52 h124 V90 h48 l28 230 H62z" fill="{fill}"/><rect x="130" y="142" width="140" height="22" fill="{dark}"/>',
        "runner": f'<path d="M20 230 q50-90 150-90 h150 q50 12 90 64 l16 36 H20z" fill="{fill}"/><path d="M20 240 h386 l-12 48 H40z" fill="{dark}"/><path d="M80 150 q40-24 90-8" fill="none" stroke="{light}" stroke-width="10"/>',
        "walker": f'<path d="M24 220 h280 q70 0 110 52 v36 H24z" fill="{fill}"/><rect x="24" y="272" width="390" height="36" fill="{dark}"/>',
        "trainer": f'<path d="M24 210 h230 l100-36 h70 v100 H24z" fill="{fill}"/><rect x="24" y="274" width="400" height="32" fill="{accent}"/><rect x="324" y="210" width="64" height="64" fill="{dark}"/>',
        "trail": f'<path d="M24 220 l48-64 h250 l100 64 v48 H24z" fill="{fill}"/><path d="M24 268 h398 v36 l-24 20 H48z" fill="{dark}"/>',
        "sport": f'<path d="M24 220 q60-76 160-70 h170 l90 70 v48 H24z" fill="{fill}"/><rect x="24" y="268" width="420" height="32" rx="8" fill="{dark}"/>',
        "sneaker": f'<path d="M28 220 h250 l130 24 v48 H28z" fill="{fill}"/><rect x="28" y="268" width="380" height="28" fill="#f4f1ee"/><path d="M140 198 h90" stroke="{dark}" stroke-width="8"/>',
        "casual_shoe": f'<path d="M24 228 h290 q70 0 110 44 v28 H24z" fill="{fill}"/><rect x="24" y="272" width="400" height="26" fill="{dark}"/><g>{laces}</g>',
        "ballet": f'<ellipse cx="200" cy="250" rx="170" ry="70" fill="{fill}"/><ellipse cx="70" cy="250" rx="48" ry="36" fill="{dark}"/><path d="M70 224 q90-70 200-16" fill="none" stroke="{light}" stroke-width="12"/>',
        "pointed_flat": f'<path d="M20 250 l230-28 170 28 v36 H20z" fill="{fill}"/><path d="M20 258 h400 v26 H20z" fill="{dark}"/>',
        "flat": f'<path d="M28 240 h360 l24 40 H28z" fill="{fill}"/><rect x="28" y="264" width="384" height="22" fill="{dark}"/>',
        "sandal": f'<rect x="36" y="268" width="328" height="24" rx="8" fill="{dark}"/><path d="M70 268 q90-90 210-16" fill="none" stroke="{fill}" stroke-width="18"/><path d="M110 266 q50 50 150 10" fill="none" stroke="{light}" stroke-width="12"/>',
        "heel": f'<path d="M40 236 h270 l90 24 v22 H40z" fill="{fill}"/><path d="M360 260 v70 l-22 10 V260z" fill="{dark}"/><path d="M90 236 q80-80 180 0" fill="none" stroke="{light}" stroke-width="12"/>',
    }
    body = drawings.get(kind, drawings["midi"])
    jewellery = {
        "jhumka",
        "drop",
        "hoop",
        "stud",
        "necklace",
        "choker",
        "bangles",
        "bracelet",
        "cuff",
        "watch",
    }
    if kind in jewellery:
        return f'<g stroke-linejoin="round" stroke-linecap="round">{body}</g>'
    return (
        f'<g fill="{fill}" stroke="{ink}" stroke-width="5" stroke-linejoin="round" '
        f'stroke-linecap="round">{body}</g>'
    )


def write_catalogue_images(products: list[Product], directory) -> None:
    """Catalogue cards use photographed JPG files; drawings are not written over them."""
    return


def product_svg(product: Product) -> str:
    fill = colour_hex(product.colour)
    ink = _ink_for(fill)
    seed = _seed(product)
    kind = _kind(product)
    name = _xml((product.product_name or product.product_id)[:28])
    ptype = _xml((product.product_type or product.category)[:24])
    colour = _xml(product.colour or "")
    paper = "#f4efe7"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400" preserveAspectRatio="xMidYMid meet" role="img" aria-label="{name}">
  <title>{name} — {ptype} · {colour}</title>
  <rect width="400" height="400" rx="28" fill="{paper}"/>
  {_pattern(product, fill, seed)}
  {_sheen(product)}
  {_draw(kind, fill, product, seed)}
</svg>
"""
