from __future__ import annotations

import unittest

from src.engine import RecommendationEngine
from src.filters import ShopperSlots
from src.telegram_ui import category_keyboard, format_turn
from src.visuals import colour_hex, visual_for
from tests.test_filters import ROOT


class VisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RecommendationEngine(catalogue_path=ROOT / "fashion_chatbot_catalogue_faqs.xlsx")
        cls.image_dir = ROOT / "web" / "product-images"

    def test_swatch_uses_listed_colour(self):
        peach = next(p for p in self.engine.products if p.product_id == "F001")
        visual = visual_for(peach)
        self.assertEqual(visual["emoji"], "👗")
        self.assertEqual(visual["accent_color"], colour_hex("Peach"))
        self.assertTrue(visual["image_url"].startswith("/static/product-images/F001.jpg"))

    def test_catalogue_images_are_unique_photos(self):
        urls = [p.image_url for p in self.engine.products]
        self.assertTrue(all(url.startswith("/static/product-images/") and url.endswith(".jpg") for url in urls))
        self.assertEqual(len(set(urls)), len(urls))
        files = []
        for product in self.engine.products:
            path = self.image_dir / f"{product.product_id}.jpg"
            self.assertTrue(path.exists(), msg=f"missing photo for {product.product_id}")
            self.assertGreater(path.stat().st_size, 8000)
            files.append(path.read_bytes())
        self.assertEqual(len(set(files)), len(files))
        tia = self.image_dir / "J004.jpg"
        amara = self.image_dir / "J014.jpg"
        self.assertNotEqual(tia.read_bytes(), amara.read_bytes())

    def test_recommendations_include_visuals_and_why(self):
        slots = ShopperSlots(occasion="casual", budget_max=2000, size="M")
        result = self.engine.handle_turn("ui", "I need casual everyday outfits, size M, budget 2000", slots)
        self.assertTrue(result.products)
        for product in result.products:
            self.assertTrue(product.get("emoji"))
            self.assertTrue(product.get("image_url"))
            self.assertTrue(product.get("why"))
            self.assertIn(".jpg", product["image_url"])
        text = format_turn(result)
        self.assertIn(result.products[0]["emoji"], text)

    def test_telegram_category_buttons_keep_titles(self):
        markup = category_keyboard()
        labels = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertTrue(any("Occasions" in label for label in labels))
        self.assertTrue(any("✨" in label for label in labels))


if __name__ == "__main__":
    unittest.main()
