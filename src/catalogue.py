from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook


@dataclass(frozen=True)
class Product:
    product_id: str
    product_name: str
    category: str
    product_type: str
    colour: str
    material: str
    sizes_raw: str
    occasions: str
    key_features: str
    price_inr: int
    stock_status: str
    style_tags: str
    care_instructions: str
    image_url: str = ""

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "category": self.category,
            "product_type": self.product_type,
            "colour": self.colour,
            "material": self.material,
            "sizes": self.sizes_raw,
            "occasions": self.occasions,
            "key_features": self.key_features,
            "price_inr": self.price_inr,
            "stock_status": self.stock_status,
            "style_tags": self.style_tags,
            "care_instructions": self.care_instructions,
            "image_url": self.image_url,
        }


@dataclass(frozen=True)
class FAQ:
    question: str
    answer: str


@dataclass(frozen=True)
class Persona:
    persona: str
    example_message: str
    goal: str
    information_to_collect: str
    bot_behaviour: str
    guardrail: str


def _parse_price(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    text = re.sub(r"[₹,\s]", "", text)
    try:
        return int(float(text))
    except ValueError:
        return 0


def load_catalogue(path: Path) -> tuple[list[Product], list[FAQ], list[Persona]]:
    wb = load_workbook(path, read_only=True, data_only=True)

    products: list[Product] = []
    ws = wb["Products"]
    rows = list(ws.iter_rows(values_only=True))
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        products.append(
            Product(
                product_id=str(row[0]).strip(),
                product_name=str(row[1] or "").strip(),
                category=str(row[2] or "").strip(),
                product_type=str(row[3] or "").strip(),
                colour=str(row[4] or "").strip(),
                material=str(row[5] or "").strip(),
                sizes_raw=str(row[6] or "").strip(),
                occasions=str(row[7] or "").strip(),
                key_features=str(row[8] or "").strip(),
                price_inr=_parse_price(row[9]),
                stock_status=str(row[10] or "").strip(),
                style_tags=str(row[11] or "").strip(),
                care_instructions=str(row[12] or "").strip(),
                image_url=str(row[13] or "").strip() if len(row) > 13 else "",
            )
        )

    faqs: list[FAQ] = []
    ws_faq = wb["FAQs"]
    for row in list(ws_faq.iter_rows(values_only=True))[1:]:
        if not row or not row[0]:
            continue
        faqs.append(FAQ(question=str(row[0]).strip(), answer=str(row[1] or "").strip()))

    personas: list[Persona] = []
    ws_p = wb["Personas"]
    for row in list(ws_p.iter_rows(values_only=True))[1:]:
        if not row or not row[0]:
            continue
        personas.append(
            Persona(
                persona=str(row[0]).strip(),
                example_message=str(row[1] or "").strip(),
                goal=str(row[2] or "").strip(),
                information_to_collect=str(row[3] or "").strip(),
                bot_behaviour=str(row[4] or "").strip(),
                guardrail=str(row[5] or "").strip(),
            )
        )

    wb.close()
    return products, faqs, personas


def default_catalogue_path() -> Path:
    env = Path(__file__).resolve().parent.parent
    return env / "fashion_chatbot_catalogue_faqs.xlsx"


def get_catalogue(catalogue_path: Optional[Path] = None) -> tuple[list[Product], list[FAQ], list[Persona]]:
    path = catalogue_path or default_catalogue_path()
    if not path.exists():
        raise FileNotFoundError(f"Catalogue not found: {path}")
    return load_catalogue(path)


STOREFRONT_CATEGORY_ORDER = (
    "Ethnic wear",
    "Western wear",
    "Jewellery",
    "Accessories",
    "Footwear",
)


def storefront_groups(products: list[Product]) -> list[dict]:
    """Preserve spreadsheet order, grouped by category then product type."""
    by_cat: dict[str, dict[str, list[Product]]] = {}
    type_order: dict[str, list[str]] = {}
    cat_order: list[str] = []
    for product in products:
        cat = product.category or "Other"
        ptype = product.product_type or "Other"
        if cat not in by_cat:
            by_cat[cat] = {}
            type_order[cat] = []
            cat_order.append(cat)
        if ptype not in by_cat[cat]:
            by_cat[cat][ptype] = []
            type_order[cat].append(ptype)
        by_cat[cat][ptype].append(product)

    ordered_cats = [name for name in STOREFRONT_CATEGORY_ORDER if name in by_cat]
    ordered_cats.extend(name for name in cat_order if name not in STOREFRONT_CATEGORY_ORDER)

    groups = []
    for cat in ordered_cats:
        types = []
        count = 0
        for ptype in type_order[cat]:
            items = by_cat[cat][ptype]
            count += len(items)
            types.append({"product_type": ptype, "products": items})
        groups.append({"category": cat, "count": count, "types": types})
    return groups
