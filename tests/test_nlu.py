from __future__ import annotations

import unittest

from src.engine import RecommendationEngine
from src.filters import ShopperSlots
from src.nlu import detect_intent, detect_sentiment, normalize
from tests.test_filters import ROOT


class NLUTests(unittest.TestCase):
    def test_typos_and_slang_are_normalized(self):
        text = normalize("gimme sneekers for offce")
        self.assertIn("sneakers", text)
        self.assertIn("office", text)
        self.assertIn("give me", text)

    def test_intents_are_not_just_keywords(self):
        self.assertEqual(detect_intent("just browsing watches"), "browse")
        self.assertEqual(detect_intent("compare flats and sandals"), "compare")
        self.assertEqual(detect_intent("I want to buy this one"), "buy")
        self.assertEqual(detect_intent("please connect me to a human"), "handoff")
        self.assertEqual(detect_intent("I need casual everyday outfits"), "shop")

    def test_sentiment_detection(self):
        self.assertEqual(detect_sentiment("this is useless and not helping"), "frustrated")
        self.assertEqual(detect_sentiment("I'm confused, what do you mean"), "confused")
        self.assertEqual(detect_sentiment("this is perfect, love this"), "excited")

    def test_engine_handles_typo_office_query(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        result = engine.handle_turn("nlu", "I need comfortable outfits for offce and daily wear", slots)
        self.assertIn("office", slots.occasion)  # "office, daily": both listed occasions are kept
        self.assertIn("budget", result.reply.lower())

    def test_compare_asks_for_named_products(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        result = engine.handle_turn("nlu", "compare flats and sandals", slots)
        self.assertEqual(result.intent, "compare")
        self.assertFalse(result.products)
        self.assertIsNone(result.comparison)
        self.assertTrue(slots.awaiting_compare)
        self.assertIn("two", result.reply.lower())

    def test_compare_table_only_for_named_catalogue_items(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        first, second = engine.products[0], engine.products[1]
        slots = ShopperSlots()
        result = engine.handle_turn("nlu", f"compare {first.product_id} and {second.product_id}", slots)
        self.assertEqual(result.intent, "compare")
        self.assertIsNotNone(result.comparison)
        self.assertEqual(len(result.comparison["headers"]), 2)
        self.assertGreaterEqual(len(result.comparison["rows"]), 3)
        ids = {item["product_id"] for item in result.products}
        self.assertEqual(ids, {first.product_id, second.product_id})
        self.assertIn("won't pick a winner", result.reply.lower())
        self.assertFalse(slots.awaiting_compare)

    def test_compare_does_not_invent_a_partner_from_the_shortlist(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        first, second = engine.products[0], engine.products[1]
        slots = ShopperSlots()
        slots.last_products = [first.to_dict(), second.to_dict()]
        result = engine.handle_turn("nlu", "I want to compare products", slots)
        self.assertIsNone(result.comparison)
        self.assertEqual(len(result.products), 0)
        self.assertTrue(slots.awaiting_compare)
        titles = [item["text"] for item in result.follow_ups]
        self.assertTrue(any(first.product_id in text for text in titles))

    def test_compare_stepwise_uses_user_picks(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        first, second = engine.products[0], engine.products[1]
        slots = ShopperSlots()
        slots.last_products = [first.to_dict(), second.to_dict()]
        first_turn = engine.handle_turn("nlu", f"compare {first.product_id}", slots)
        self.assertIsNone(first_turn.comparison)
        self.assertEqual(slots.compare_ids, [first.product_id])
        second_turn = engine.handle_turn("nlu", second.product_id, slots)
        self.assertIsNotNone(second_turn.comparison)
        ids = {item["product_id"] for item in second_turn.products}
        self.assertEqual(ids, {first.product_id, second.product_id})

    def test_compare_these_uses_the_shown_shortlist(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        first, second = engine.products[0], engine.products[1]
        slots = ShopperSlots()
        slots.last_products = [first.to_dict(), second.to_dict()]
        result = engine.handle_turn("nlu", "compare these", slots)
        self.assertIsNotNone(result.comparison)
        ids = {item["product_id"] for item in result.products}
        self.assertEqual(ids, {first.product_id, second.product_id})

    def test_buy_starts_checkout(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        result = engine.handle_turn("nlu", "I want to buy Aura Minimal Analogue Watch", slots)
        self.assertEqual(result.intent, "buy")
        self.assertTrue(result.products)
        self.assertIn("check out", result.reply.lower())
        self.assertNotIn("mock", result.reply.lower())
        self.assertNotIn("demo", result.reply.lower())
        self.assertNotIn("cannot place an order", result.reply.lower())
        self.assertEqual(slots.checkout_step, "name")
        titles = [item["title"] for item in result.follow_ups]
        self.assertIn("Cancel", titles)

    def test_repeated_frustration_triggers_handoff(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        first = engine.handle_turn("nlu", "this is useless", slots)
        self.assertEqual(first.sentiment, "frustrated")
        self.assertFalse(first.handoff)
        second = engine.handle_turn("nlu", "still not helping", slots)
        self.assertTrue(second.handoff)
        self.assertIn("human", second.reply.lower())
        titles = [item["title"] for item in second.follow_ups]
        self.assertIn("Talk to a person", titles)

    def test_explicit_human_request(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        result = engine.handle_turn("nlu", "Please connect me to a human", slots)
        self.assertTrue(result.handoff)
        self.assertEqual(result.intent, "handoff")

    def test_recommendations_include_a_back_chip(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        result, slots = None, ShopperSlots()
        result = engine.handle_turn("nlu", "office necklace under 2000", slots)
        if not result.products:
            result = engine.handle_turn("nlu", "I prefer a minimal style", slots)
        self.assertTrue(result.products)
        titles = [item["title"] for item in result.follow_ups]
        self.assertIn("Back", titles)
        self.assertEqual(result.follow_ups[0]["text"], "Go back")

    def test_go_back_returns_type_then_main_menu(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        engine.handle_turn("nlu", "office necklace under 2000", slots)
        first = engine.handle_turn("nlu", "Go back", slots)
        self.assertEqual(slots.product_type, None)
        self.assertEqual(first.products, [])
        titles = [item["title"] for item in first.follow_ups]
        self.assertIn("Back", titles)
        self.assertIn("Necklace", titles)
        self.assertIn("Earrings", titles)
        second = engine.handle_turn("nlu", "Go back", slots)
        main = [item["title"] for item in second.follow_ups]
        self.assertIn("Occasions", main)
        self.assertIn("Accessories", main)
        self.assertIn("Footwear", main)


if __name__ == "__main__":
    unittest.main()
