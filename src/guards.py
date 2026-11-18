"""Output guards for LLM-written replies.

The LLM may only reword catalogue facts.  Anything that looks like an invented price, a delivery
promise, an injury/medical claim, a precious-metal claim or bridal styling is rejected and the
engine falls back to its deterministic template reply.
"""

from __future__ import annotations

import re
from typing import List, Optional

_AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:rupees|rs\b|inr\b)", re.I)
_DELIVERY = re.compile(
    r"\b(deliver(?:y|ed|s)?|arrive[sd]?|ship(?:ped|s|ping)?|dispatch(?:ed)?)\b[^.\n]{0,50}"
    r"\b(\d+|tomorrow|today|tonight|weekend|saturday|sunday|monday|tuesday|wednesday|thursday|friday|days?|hours?|express|same[- ]day)\b",
    re.I,
)
_INJURY = re.compile(
    r"\b(prevent\w*|avoid\w*|reduc\w*|protect\w*|lower\w*|help\w*\s+with|relie\w*)\b[^.\n]{0,25}\b(injur\w*|pain|strain|shin splints|knee|joint)\b"
    r"|\binjury[- ]free\b|\borthop\w*|\bmedical(ly)?\b|\bpodiatr\w*",
    re.I,
)
_PRECIOUS = re.compile(
    r"\b(real|genuine|pure|solid|sterling|hallmarked|authentic|18k|22k|24k|925|14k)\b[^.\n]{0,15}\b(gold|silver|pearls?|diamonds?|platinum)\b",
    re.I,
)
_NEGATION_BEFORE = re.compile(r"(not|n't|no|never|without|isn’t|isnt)\s+(?:\w+\s+){0,3}$", re.I)


def _amount_values(text: str) -> List[int]:
    values = []
    for m in _AMOUNT.finditer(text):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        if not raw:
            continue
        try:
            values.append(int(float(raw)))
        except ValueError:
            continue
    return values


def strip_markdown(text: str) -> str:
    """The chat UI shows plain text, so drop markdown emphasis/headings/bullets."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\s)([^*\n]+?)\*(?!\*)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*]\s+", "• ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def has_markdown_table(text: str) -> bool:
    rows = [ln for ln in text.splitlines() if ln.strip().startswith("|") and ln.count("|") >= 2]
    return len(rows) >= 2


def violation(reply: str, products: List[dict], budget_max: Optional[int] = None, user_text: str = "") -> Optional[str]:
    """Return a short reason if ``reply`` must not be shown, else None."""
    if not reply or not reply.strip():
        return "empty"
    if len(reply) > 1500:
        return "too long"
    if has_markdown_table(reply):
        return "markdown table"
    allowed = {int(p["price_inr"]) for p in products if p.get("price_inr") is not None}
    if budget_max is not None:
        allowed.add(int(budget_max))
    for value in _amount_values(reply):
        if value not in allowed:
            return f"amount {value} not in catalogue"
    if _DELIVERY.search(reply):
        return "delivery promise"
    if _INJURY.search(reply):
        return "injury/medical claim"
    for m in _PRECIOUS.finditer(reply):
        if not _NEGATION_BEFORE.search(reply[: m.start()][-30:]):
            return "precious metal claim"
    if re.search(r"\b(bridal|bride)\b", reply, re.I) and not re.search(r"\b(bridal|bride)\b", user_text, re.I):
        return "bridal styling"
    ranges = re.findall(r"UK\s*(\d+)\s*[–-]\s*(\d+)", reply)
    if ranges:
        listed = set()
        for p in products:
            listed.update(re.findall(r"UK\s*(\d+)\s*[–-]\s*(\d+)", str(p.get("sizes", ""))))
        if any(r not in listed for r in ranges):
            return "size range not in catalogue"
    return None


def ensure_low_stock_noted(reply: str, products: List[dict]) -> str:
    """Low stock must be stated: append a note if the LLM left it out."""
    low = [p["product_name"] for p in products if str(p.get("stock_status", "")).lower() == "low stock"]
    if low and "low stock" not in reply.lower():
        names = " and ".join(low)
        verb = "is" if len(low) == 1 else "are"
        reply = f"{reply.rstrip()}\n\nNote: {names} {verb} listed as Low stock."
    return reply
