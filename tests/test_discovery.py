from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.engine import RecommendationEngine
from src.filters import ShopperSlots, explain_match
from src.session import SessionStore
from tests.test_filters import ROOT


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")

    def test_asks_one_preference_at_a_time(self):
        slots = ShopperSlots()
        first = self.engine.handle_turn("d", "I need casual everyday outfits.", slots)
        self.assertIn("budget", first.reply.lower())
        self.assertNotIn("size", first.reply.lower())
        second = self.engine.handle_turn("d", "My maximum budget is 2000 rupees", slots)
        self.assertEqual(slots.budget_max, 2000)
        self.assertIn("size", second.reply.lower())
        self.assertNotIn("maximum budget", second.reply.lower())

    def test_why_mentions_user_criteria(self):
        slots = ShopperSlots(occasion="casual", budget_max=2000, size="M")
        product = next(p for p in self.engine.products if p.product_id == "F010")
        why = explain_match(product, slots)
        self.assertIn("₹2000", why)
        self.assertIn("casual", why.lower())
        self.assertIn("size M", why)
        result = self.engine.handle_turn("d", "I need casual everyday outfits, size M, budget 2000", slots)
        self.assertTrue(result.products)
        self.assertTrue(all(p.get("why") for p in result.products))
        self.assertIn("recommended because", result.products[0]["why"].lower())
        self.assertIn("saved preferences", result.reply.lower())
        for product in result.products:
            self.assertIn(product["product_name"], result.reply)
            self.assertIn(product["product_id"], result.reply)

    def test_session_memory_keeps_budget_and_refines(self):
        path = Path(tempfile.mkdtemp()) / "sessions.json"
        store = SessionStore(path)
        slots = store.get("mem")
        self.engine.handle_turn("mem", "I need casual everyday outfits. Size M. Budget 2000 rupees.", slots)
        store.update("mem", slots)
        again = store.get("mem")
        self.assertEqual(again.budget_max, 2000)
        self.assertEqual(again.size, "M")
        self.assertEqual(again.occasion, "casual")
        cheaper = self.engine.handle_turn("mem", "Show me cheaper options", again)
        self.assertIsNotNone(again.budget_max)
        self.assertLess(again.budget_max, 2000)
        self.assertTrue(cheaper.products or "couldn't find" in cheaper.reply.lower())
        self.assertNotIn("what is the outfit for", cheaper.reply.lower())

    def test_festive_chip_is_not_cleared_by_llm_change_field(self):
        class FakeLLM:
            available = True
            provider = "groq"
            model = "openai/gpt-oss-120b"

            def parse_message(self, message, context):
                return {
                    "intent": "change_requirement",
                    "change_field": "occasion",
                    "sentiment": "neutral",
                }

            def compose_reply(self, context, products, instruction):
                return "What is the outfit for — wedding guest, office, party, or something else?"

        engine = RecommendationEngine(
            catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx",
            grok=FakeLLM(),
        )
        slots = ShopperSlots(
            last_question_asked="What is the outfit for — wedding guest, office, party, or something else?"
        )
        result = engine.handle_turn("d", "It's for a festive occasion", slots)
        self.assertEqual(slots.occasion, "festive")
        self.assertIn("budget", result.reply.lower())
        self.assertNotIn("what is the outfit for", result.reply.lower())

    def test_recommendations_only_use_spreadsheet_ids(self):
        slots = ShopperSlots(occasion="festive", budget_max=10000, size="M")
        result = self.engine.handle_turn(
            "d",
            "It's for a festive occasion. Size M. Budget 10000 rupees.",
            slots,
        )
        self.assertTrue(result.products)
        catalogue_ids = {p.product_id for p in self.engine.products}
        for product in result.products:
            self.assertIn(product["product_id"], catalogue_ids)
            self.assertLessEqual(product["price_inr"], 10000)


if __name__ == "__main__":
    unittest.main()
