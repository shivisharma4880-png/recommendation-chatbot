"""Shared starter chips for web-equivalent Telegram browsing."""

from __future__ import annotations

CATEGORIES = [
    {
        "title": "Occasions",
        "emoji": "✨",
        "children": [
            {"title": "Office wear", "emoji": "💼", "text": "I need comfortable outfits for office and daily wear."},
            {"title": "Festive", "emoji": "🪔", "text": "I need an outfit for a festive occasion."},
            {"title": "Sports", "emoji": "🏃", "text": "I need an outfit for sports or gym."},
            {"title": "Casuals", "emoji": "☀️", "text": "I need casual everyday outfits."},
        ],
    },
    {
        "title": "Accessories",
        "emoji": "💎",
        "children": [
            {"title": "Necklace", "emoji": "📿", "text": "Show me necklaces from the catalogue."},
            {"title": "Earrings", "emoji": "💍", "text": "Show me earrings from the catalogue."},
            {"title": "Bracelets", "emoji": "⭕", "text": "Show me bracelets from the catalogue."},
            {"title": "Watches", "emoji": "⌚", "text": "Show me watches from the catalogue."},
        ],
    },
    {
        "title": "Footwear",
        "emoji": "👟",
        "children": [
            {"title": "Sports shoes", "emoji": "🏃", "text": "Suggest sports shoes for running or gym."},
            {"title": "Flats", "emoji": "🥿", "text": "Show me flats from the catalogue."},
            {"title": "Sandals", "emoji": "👡", "text": "Show me sandals from the catalogue."},
            {"title": "Casual shoes", "emoji": "👟", "text": "Show me casual shoes or sneakers from the catalogue."},
        ],
    },
]


def category_titles() -> list[str]:
    return [item["title"] for item in CATEGORIES]


def category_children(title: str) -> list[dict]:
    for item in CATEGORIES:
        if item["title"] == title:
            return list(item["children"])
    return []
