from __future__ import annotations

import unittest

from src.chips import category_children, category_titles
from src.engine import RecommendationEngine, TurnResult
from src.filters import ShopperSlots
from src.telegram_ui import category_keyboard, followup_keyboard, format_preferences, format_turn
from tests.test_filters import ROOT


class TelegramUiTests(unittest.TestCase):
    def test_category_chips_exist(self):
        titles = category_titles()
        self.assertEqual(titles, ["Occasions", "Accessories", "Footwear"])
        self.assertTrue(category_children("Occasions"))
        markup = category_keyboard()
        self.assertEqual(len(markup.inline_keyboard), 3)

    def test_followup_keyboard_indexes_callbacks(self):
        markup = followup_keyboard(
            [
                {"title": "Budget", "text": "I want to change my budget"},
                {"title": "Size", "text": "I want to change my size"},
            ]
        )
        self.assertIsNotNone(markup)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "fu:0")
        self.assertEqual(markup.inline_keyboard[0][1].callback_data, "fu:1")

    def test_format_turn_prefers_comparison_table(self):
        result = TurnResult(
            reply="Here's a catalogue-only comparison of two items.",
            products=[
                {"product_id": "J004", "product_name": "Tia Rose Gold Minimal Chain"},
                {"product_id": "J010", "product_name": "Anvi Crystal Studs"},
            ],
            comparison={
                "headers": ["Tia Rose Gold Minimal Chain (J004)", "Anvi Crystal Studs (J010)"],
                "rows": [{"label": "Price", "values": ["₹599", "₹4499"]}],
            },
        )
        text = format_turn(result)
        self.assertIn("<b>Comparison</b>", text)
        self.assertIn("₹599", text)
        self.assertIn("Anvi Crystal Studs (J010)", text)

    def test_format_turn_prefers_confirmation_receipt(self):
        result = TurnResult(
            reply="Order confirmed for Aarohi Peach Anarkali (F001). Reference ORD-F001.",
            products=[{"product_id": "F001", "product_name": "Aarohi Peach Anarkali"}],
            confirmation={
                "reference": "ORD-F001",
                "product_id": "F001",
                "product_name": "Aarohi Peach Anarkali",
                "price_inr": 4999,
                "colour": "Peach",
                "size": "M",
                "name": "Riya Sharma",
                "address": "Mumbai",
                "payment": "UPI",
            },
        )
        text = format_turn(result)
        self.assertIn("<b>Order confirmation</b>", text)
        self.assertIn("ORD-F001", text)
        self.assertIn("Riya Sharma", text)
        self.assertIn("📏", text)
        self.assertIn("💳", text)

    def test_format_turn_includes_products(self):
        result = TurnResult(
            reply="Here are options from our catalogue:",
            products=[
                {
                    "product_id": "F010",
                    "product_name": "Riya Lavender Shirt Dress",
                    "price_inr": 1999,
                    "sizes": "XS, S, M, L",
                    "stock_status": "In stock",
                    "colour": "Lavender",
                    "key_features": "Button-down; waist tie",
                }
            ],
        )
        text = format_turn(result)
        self.assertIn("F010", text)
        self.assertIn("1999", text)
        self.assertIn("<b>Riya Lavender Shirt Dress</b>", text)

    def test_format_preferences(self):
        slots = ShopperSlots(occasion="casual", budget_max=2000, size="M")
        text = format_preferences(slots)
        self.assertIn("₹2000", text)
        self.assertIn("Size: M", text)

    def test_engine_saves_follow_ups_on_session(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        result = engine.handle_turn("tg", "I need casual everyday outfits.", slots)
        self.assertTrue(result.follow_ups)
        self.assertEqual(slots.last_follow_ups, result.follow_ups)
        self.assertIn("budget", (slots.last_question_asked or "").lower())


if __name__ == "__main__":
    unittest.main()
