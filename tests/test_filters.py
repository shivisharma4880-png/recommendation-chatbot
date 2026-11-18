from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from src.catalogue import get_catalogue, storefront_groups
from src.filters import ShopperSlots, filter_products, rank_products, size_matches
from src.engine import RecommendationEngine


ROOT = Path(__file__).resolve().parent.parent


class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.products, cls.faqs, _ = get_catalogue(ROOT / "fashion_chatbot_catalogue_faqs.xlsx")

    def test_catalogue_loads_all_spreadsheet_products(self):
        self.assertEqual(len(self.products), 76)

    def test_storefront_groups_every_spreadsheet_product(self):
        groups = storefront_groups(self.products)
        ids = [
            product.product_id
            for group in groups
            for block in group["types"]
            for product in block["products"]
        ]
        self.assertEqual(len(ids), 76)
        self.assertEqual(len(set(ids)), 76)
        self.assertEqual([group["category"] for group in groups], [
            "Ethnic wear",
            "Western wear",
            "Jewellery",
            "Accessories",
            "Footwear",
        ])
        counts = {group["category"]: group["count"] for group in groups}
        self.assertEqual(counts["Ethnic wear"], 20)
        self.assertEqual(counts["Western wear"], 23)
        self.assertEqual(counts["Jewellery"], 16)
        self.assertEqual(counts["Footwear"], 13)
        self.assertEqual(sum(counts.values()), 76)

    def test_catalogue_payload_covers_spreadsheet(self):
        from src.web import catalogue_payload

        data = catalogue_payload()
        self.assertEqual(data["count"], 76)
        products = [
            product
            for group in data["categories"]
            for block in group["types"]
            for product in block["products"]
        ]
        self.assertEqual(len(products), 76)
        self.assertTrue(all(product.get("image_url") for product in products))
        self.assertTrue(all(product.get("product_name") for product in products))

    def test_category_faqs_are_present(self):
        questions = " ".join(faq.question.lower() for faq in self.faqs)
        for needle in (
            "office wear",
            "festive outfit",
            "gym or sports",
            "casual everyday",
            "necklace",
            "earrings",
            "bracelet",
            "watch",
            "flats",
            "sandals",
            "sneakers",
            "sports shoes",
        ):
            self.assertIn(needle, questions)

    def test_shoe_size_in_range(self):
        shoe = next(p for p in self.products if p.product_id == "S001")
        self.assertTrue(size_matches(shoe, "UK 6"))
        self.assertFalse(size_matches(shoe, "UK 12"))

    def test_budget_under_10000_wedding(self):
        slots = ShopperSlots(occasion="wedding", budget_max=10000, size="M")
        matches = filter_products(self.products, slots)
        ids = {p.product_id for p in matches}
        self.assertIn("F001", ids)
        self.assertIn("F003", ids)  # ₹8999 within ₹10,000
        over = [p for p in matches if p.price_inr > 10000]
        self.assertEqual(over, [])

    def test_office_budget_2000_excludes_kurta(self):
        slots = ShopperSlots(occasion="office", budget_max=2000, size="M", category="Ethnic wear")
        matches = filter_products(self.products, slots)
        ids = {p.product_id for p in matches}
        self.assertNotIn("F007", ids)  # ₹2199

    def test_cocktail_under_3000(self):
        slots = ShopperSlots(occasion="cocktail", budget_max=3000, size="M")
        matches = rank_products(filter_products(self.products, slots), slots, limit=5)
        for p in matches:
            self.assertLessEqual(p.price_inr, 3000)

    def test_running_gym_under_4000(self):
        slots = ShopperSlots(
            category="Footwear",
            activity="running gym",
            budget_max=4000,
            size="UK 6",
            outfit_priority="running",
        )
        matches = filter_products(self.products, slots)
        self.assertTrue(matches)
        for p in matches:
            self.assertLessEqual(p.price_inr, 4000)
            self.assertIn("running", (p.occasions + p.product_type).lower())

    def test_gift_jewellery_under_2500(self):
        slots = ShopperSlots(category="Jewellery", budget_max=2500)
        matches = filter_products(self.products, slots, include_accessories=True)
        for p in matches:
            self.assertLessEqual(p.price_inr, 2500)

    def test_no_match_budget_message(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots(occasion="wedding", budget_max=500, size="M")
        reply = engine.handle_message("t", "wedding guest size M under 500", slots)
        self.assertIn("budget", reply.lower())

    def test_necklace_and_earrings_types(self):
        necklaces = filter_products(
            self.products,
            ShopperSlots(category="Jewellery", product_type="necklace"),
            include_accessories=True,
        )
        self.assertTrue({p.product_id for p in necklaces} & {"J003", "J004"})
        earrings = filter_products(
            self.products,
            ShopperSlots(category="Jewellery", product_type="earrings"),
            include_accessories=True,
        )
        self.assertTrue({p.product_id for p in earrings} & {"J001", "J002"})

    def test_office_necklace_styles_are_distinct(self):
        base = ShopperSlots(
            category="Jewellery",
            product_type="necklace",
            occasion="office",
            budget_max=2000,
        )
        matches = filter_products(self.products, base, include_accessories=True)
        self.assertGreaterEqual(len(matches), 3)
        minimal = rank_products(matches, replace(base, style="minimal"), limit=3)
        traditional = rank_products(matches, replace(base, style="traditional"), limit=3)
        statement = rank_products(matches, replace(base, style="statement"), limit=3)
        self.assertTrue(minimal)
        self.assertTrue(traditional)
        self.assertNotEqual(minimal[0].product_id, traditional[0].product_id)
        self.assertNotEqual(minimal[0].product_id, statement[0].product_id)
        self.assertIn("minimal", minimal[0].style_tags.lower())
        self.assertIn("traditional", traditional[0].style_tags.lower())

    def test_ui_categories_have_catalogue_matches(self):
        cases = [
            ShopperSlots(occasion="office"),
            ShopperSlots(occasion="festive"),
            ShopperSlots(activity="gym"),
            ShopperSlots(occasion="casual"),
            ShopperSlots(category="Jewellery", product_type="necklace"),
            ShopperSlots(category="Jewellery", product_type="earrings"),
            ShopperSlots(category="Jewellery", product_type="bracelet"),
            ShopperSlots(category="Accessories", product_type="watch"),
            ShopperSlots(category="Footwear", product_type="sports shoes"),
            ShopperSlots(category="Footwear", product_type="flats"),
            ShopperSlots(category="Footwear", product_type="sandals"),
            ShopperSlots(category="Footwear", product_type="sneakers"),
        ]
        for slots in cases:
            include_acc = (slots.category or "") in {"Jewellery", "Accessories"}
            matches = filter_products(self.products, slots, include_accessories=include_acc)
            self.assertTrue(matches, msg=f"no products for {slots}")

    def _types(self, product_type, **kwargs):
        slots = ShopperSlots(category="Footwear", product_type=product_type, **kwargs)
        return filter_products(self.products, slots)

    def test_shoes_do_not_mix_sandals_or_flats(self):
        for ptype in ("shoes", "sneakers", "casual shoes", "sports shoes"):
            matches = self._types(ptype)
            self.assertTrue(matches, msg=f"no products for {ptype}")
            for product in matches:
                blob = f"{product.product_type} {product.product_name}".lower()
                self.assertNotIn("sandal", blob, msg=f"{ptype} leaked {product.product_id}")
                self.assertNotIn("flat", blob, msg=f"{ptype} leaked {product.product_id}")
        sneakers = {p.product_id for p in self._types("sneakers")}
        self.assertEqual(sneakers, {"S005", "S012", "S013"})
        sports = {p.product_id for p in self._types("sports shoes")}
        self.assertIn("S002", sports)  # walking shoes stay with sports, not casual sneakers
        self.assertTrue(sports.isdisjoint({"S005", "S010", "S011", "S012", "S013"}))
        sandals = {p.product_id for p in self._types("sandals")}
        self.assertEqual(sandals, {"S010", "S011"})
        flats = {p.product_id for p in self._types("flats")}
        self.assertEqual(flats, {"S008", "S009"})
        shoes = {p.product_id for p in self._types("shoes")}
        self.assertTrue(shoes)
        self.assertTrue(shoes.isdisjoint({"S008", "S009", "S010", "S011"}))

    def test_shirt_does_not_mix_tshirts_or_shirt_dresses(self):
        matches = filter_products(self.products, ShopperSlots(category="Western wear", product_type="shirt"))
        self.assertTrue(matches)
        for product in matches:
            blob = f"{product.product_type} {product.product_name}".lower()
            self.assertIn("shirt", blob)
            self.assertNotIn("dress", blob)
            self.assertNotIn("tee", blob)
            self.assertNotIn("t-shirt", blob)

    def test_casual_shoes_recommendation_excludes_sandals(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        engine.handle_turn("t", "Show me casual shoes or sneakers from the catalogue.", slots)
        engine.handle_turn("t", "10000", slots)
        result = engine.handle_turn("t", "UK 5", slots)
        self.assertTrue(result.products)
        for product in result.products:
            blob = f"{product.get('product_type', '')} {product.get('product_name', '')}".lower()
            self.assertNotIn("sandal", blob)
            self.assertNotIn("flat", blob)

    def test_bare_budget_moves_past_budget_question(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        first = engine.handle_turn("t", "I need casual everyday outfits.", slots)
        self.assertIn("budget", first.reply.lower())
        titles = [item["title"] for item in first.follow_ups]
        self.assertIn("Under ₹1,000", titles)
        second = engine.handle_turn("t", "1000", slots)
        self.assertEqual(slots.budget_max, 1000)
        self.assertNotIn("maximum budget", second.reply.lower())
        self.assertIn("size", second.reply.lower())
        rupee_slots = ShopperSlots(occasion="casual", last_question_asked="What is your maximum budget in INR?")
        engine.handle_turn("t", "1000 rupees", rupee_slots)
        self.assertEqual(rupee_slots.budget_max, 1000)

    def test_budget_chip_text_parses(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots(occasion="casual", last_question_asked="What is your maximum budget in INR?")
        result = engine.handle_turn("t", "My maximum budget is 2000 rupees", slots)
        self.assertEqual(slots.budget_max, 2000)
        self.assertNotIn("maximum budget", result.reply.lower())

    def test_change_budget_after_no_match(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots(occasion="casual", budget_max=500, size="M")
        first = engine.handle_turn("t", "I need casual everyday outfits. Size M. Budget 500 rupees.", slots)
        self.assertIn("couldn't find", first.reply.lower())
        titles = [item["title"] for item in first.follow_ups]
        self.assertIn("Budget", titles)
        second = engine.handle_turn("t", "budget", slots)
        self.assertIsNone(slots.budget_max)
        self.assertIn("budget", second.reply.lower())
        self.assertNotIn("couldn't find", second.reply.lower())
        chip_titles = [item["title"] for item in second.follow_ups]
        self.assertIn("Under ₹2,000", chip_titles)

    def test_faq_delivery_no_invention(self):
        engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        slots = ShopperSlots()
        reply = engine.handle_message("t", "How long will delivery take?", slots)
        self.assertIn("PIN code", reply)
        self.assertNotRegex(reply, r"\d+\s*day")


if __name__ == "__main__":
    unittest.main()
