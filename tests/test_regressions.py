"""Regression tests for the QA pass (see QA_REPORT.md). All run offline: DISABLE_LLM=1 or a FakeLLM."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from src.engine import RecommendationEngine
from src.faq_match import match_faq
from src.filters import ShopperSlots
from src.guards import has_markdown_table, strip_markdown, violation
from src.nlu import understand
from src.normalize import (
    canonical_category,
    canonical_product_type,
    normalize_category_and_type,
    normalize_occasion,
    parse_sizes,
)
from src.session import SessionStore


class FakeLLM:
    available = True
    provider = "groq"
    model = "fake"

    def __init__(self, parsed=None, reply=None, fail_parse=False):
        self.parsed = parsed or {}
        self.reply = reply
        self.fail_parse = fail_parse

    def parse_message(self, message, context):
        if self.fail_parse:
            raise RuntimeError("boom")
        return dict(self.parsed)

    def compose_reply(self, context, products, instruction):
        if self.reply is None:
            raise RuntimeError("no reply")
        return self.reply


def run(engine, *messages, slots=None):
    slots = slots or ShopperSlots()
    result = None
    for message in messages:
        result = engine.handle_turn("t", message, slots)
    return result, slots


def ids(result):
    return [p["product_id"] for p in result.products]


ENGINE = RecommendationEngine()


class SlotCanonicalisationTests(unittest.TestCase):
    def test_llm_free_text_slots_are_canonicalised(self):
        self.assertEqual(canonical_category("Ethnic"), "Ethnic wear")
        self.assertEqual(canonical_category("western"), "Western wear")
        self.assertEqual(canonical_product_type("Kurta / Kurti"), "kurta")
        self.assertEqual(canonical_product_type("running shoes"), "sports shoes")
        self.assertEqual(normalize_occasion("Wedding guest"), "wedding")
        self.assertEqual(normalize_category_and_type("Ethnic", "kurta"), ("Ethnic wear", "kurta"))

    def test_llm_messy_slots_still_find_products(self):
        llm = FakeLLM({"category": "Ethnic", "product_type": "Kurta", "occasion": "Office wear", "budget_max": "₹3,000", "size": "m"})
        engine = RecommendationEngine(grok=llm)
        result, slots = run(engine, "I need a kurta for office under 3000, size M")
        self.assertTrue(result.products)
        self.assertEqual(slots.category, "Ethnic wear")
        self.assertEqual(slots.size, "M")
        self.assertEqual(slots.budget_max, 3000)

    def test_llm_cannot_invent_product_type_or_colour(self):
        engine = RecommendationEngine(grok=FakeLLM({"product_type": "kurta", "category": "Ethnic wear", "colour": "red"}))
        _, slots = run(engine, "office wear under 2000", "M")
        result, slots = run(engine, "show me options", slots=slots)
        self.assertIsNone(slots.product_type)
        self.assertIsNone(slots.colour)

    def test_llm_invented_budget_is_ignored(self):
        engine = RecommendationEngine(grok=FakeLLM({"budget_max": 99999}))
        _, slots = run(engine, "I need a casual outfit")
        self.assertIsNone(slots.budget_max)


class NLUTests(unittest.TestCase):
    def test_shades_is_not_shoes_and_match_is_not_watch(self):
        self.assertNotEqual(understand("what shades do you have").slots.get("product_type"), "sports shoes")
        self.assertIsNone(understand("something to match my outfit").slots.get("product_type"))

    def test_substring_colour_not_matched(self):
        self.assertNotEqual(understand("what is the distance").slots.get("colour"), "tan")

    def test_size_l_does_not_match_xl_only(self):
        self.assertEqual(parse_sizes("XL"), ["XL"])
        self.assertEqual(parse_sizes("M or L"), ["M", "L"])


class FilterAndFlowTests(unittest.TestCase):
    def test_persona1_office_kurta(self):
        result, slots = run(ENGINE, "I need a kurta for office under 3000", "M")
        self.assertTrue(result.products)
        for p in result.products:
            self.assertLessEqual(int(p["price_inr"]), 3000)
            self.assertIn("M", p["sizes"])

    def test_budget_boundary_is_inclusive(self):
        result, _ = run(ENGINE, "indigo casual kurta under 1299", "M")
        self.assertIn("F019", ids(result))  # ₹1299 exactly
        result, _ = run(ENGINE, "indigo casual kurta under 1298", "M")
        self.assertNotIn("F019", ids(result))

    def test_unstocked_size_is_reported_not_faked(self):
        result, _ = run(ENGINE, "I need a kurta for office under 3000", "XXS")
        self.assertEqual(result.products, [])
        self.assertIn("size", result.reply.lower())

    def test_shoe_size_out_of_range(self):
        result, _ = run(ENGINE, "running shoes under 4000", "UK 12")
        self.assertEqual(result.products, [])

    def test_bangle_size_asked_and_unlisted_size_not_ignored(self):
        result, slots = run(ENGINE, "I want bangles under 1500")
        self.assertIn("bangle size", result.reply.lower())
        self.assertIsNone(slots.budget_max and None)
        self.assertEqual(slots.budget_max, 1500)  # 2.6 is a size, not a budget
        result, slots = run(ENGINE, "2.6", slots=slots)
        self.assertEqual(slots.budget_max, 1500)
        self.assertEqual(ids(result), ["J005"])
        result, _ = run(ENGINE, "I want bangles under 1500", "2.2")
        self.assertEqual(result.products, [])

    def test_no_match_budget_message_names_an_outfit_not_an_accessory(self):
        result, _ = run(ENGINE, "wedding outfit under 500", "M")
        self.assertEqual(result.products, [])
        self.assertIn("budget", result.reply.lower())
        self.assertNotIn("Earrings", result.reply)
        self.assertRegex(result.reply, r"₹\d+")

    def test_low_stock_is_stated(self):
        result, _ = run(ENGINE, "wedding lehenga under 9000 size M")
        self.assertIn("F003", ids(result))
        self.assertTrue(set(ids(result)) <= {"F003", "F024"})
        self.assertIn("Low stock", result.reply)

    def test_one_question_at_a_time(self):
        result, slots = run(ENGINE, "I need something nice")
        self.assertIn("outfit for", result.reply.lower())
        result, slots = run(ENGINE, "office", slots=slots)
        self.assertEqual(result.reply.count("?"), 1)

    def test_mid_chat_budget_and_size_updates(self):
        result, slots = run(ENGINE, "office wear under 2000", "M", "actually make it 1700")
        self.assertEqual(slots.budget_max, 1700)
        self.assertEqual(slots.size, "M")
        for p in result.products:
            self.assertLessEqual(int(p["price_inr"]), 1700)
        result, slots = run(ENGINE, "change size to L", slots=slots)
        self.assertEqual(slots.size, "L")
        self.assertEqual(slots.budget_max, 1700)

    def test_colour_with_no_match_blames_colour(self):
        result, slots = run(ENGINE, "office wear under 1700", "M", "show me in black")
        self.assertEqual(result.products, [])
        self.assertIn("colour", result.reply.lower())

    def test_accessory_offer_once_and_not_before_outfits(self):
        result, slots = run(ENGINE, "I need a wedding guest outfit under 10000")
        self.assertNotIn("jewellery", result.reply.lower())
        result, slots = run(ENGINE, "M", slots=slots)
        self.assertEqual(len(result.products), 3)
        self.assertIn("jewellery", result.reply.lower())
        result, slots = run(ENGINE, "no thanks", slots=slots)
        self.assertEqual(result.products, [])
        result, slots = run(ENGINE, "change budget to 9000", slots=slots)
        self.assertNotIn("matching jewellery", result.reply.lower())

    def test_accessory_yes_shows_jewellery_and_cheaper_dresses_uses_outfit_prices(self):
        result, slots = run(ENGINE, "I need a wedding guest outfit under 10000", "M", "yes please")
        self.assertTrue(all(p["category"] in ("Jewellery", "Accessories") for p in result.products))
        result, slots = run(ENGINE, "show me cheaper dresses", slots=slots)
        self.assertGreater(slots.budget_max, 1000)  # not capped to the earrings' price

    def test_show_me_does_not_trigger_accessory_yes(self):
        result, slots = run(ENGINE, "festive outfit under 8000", "M", "Show me similar options to Aarohi Peach Anarkali")
        self.assertTrue(result.products)
        self.assertTrue(all(p["category"] in ("Ethnic wear", "Western wear") for p in result.products))
        self.assertNotIn("F001", ids(result))
        self.assertIsNone(slots.colour)  # "Peach" belongs to the product name

    def test_new_product_type_clears_stale_category(self):
        result, slots = run(ENGINE, "wedding lehenga under 9000", "M", "party ke liye dress dikhao 3000 tak")
        self.assertTrue(result.products)
        self.assertNotEqual(slots.category, "Ethnic wear")

    def test_hinglish(self):
        result, slots = run(ENGINE, "mujhe shaadi ke liye lehenga chahiye 9000 ke andar", "M size")
        self.assertTrue(set(ids(result)) <= {"F003", "F024"})
        self.assertIn("F003", ids(result))

    def test_typos(self):
        result, _ = run(ENGINE, "i want sandels under 1500 UK 6")
        self.assertEqual(ids(result), ["S010"])
        result, _ = run(ENGINE, "I need a cocktial dres below 3000, size M")
        self.assertTrue(result.products)

    def test_running_vs_gym_priority_question(self):
        result, _ = run(ENGINE, "I need an outfit for running and gym under 3000", "M")
        self.assertIn("running", result.reply.lower())
        self.assertIn("gym", result.reply.lower())
        self.assertIn("?", result.reply)

    def test_outfit_request_excludes_footwear(self):
        result, _ = run(ENGINE, "I need a casual outfit under 2000", "M")
        self.assertTrue(result.products)
        self.assertTrue(all(p["category"] != "Footwear" for p in result.products))


class PersonaFlowTests(unittest.TestCase):
    def test_p1_wedding_guest(self):
        result, slots = run(
            ENGINE,
            "I need a dress for my sister's wedding. My budget is under ₹10,000.",
            "Traditional, but not too heavy.",
            "M or L. Peach or pastel shades.",
        )
        self.assertTrue(result.products)
        self.assertEqual(slots.budget_max, 10000)
        for p in result.products:
            self.assertLessEqual(int(p["price_inr"]), 10000)
        self.assertIn("jewellery", result.reply.lower())  # one accessory offer after the shortlist

    def test_p2_styling_never_filters_by_skin_tone_or_owned_colour(self):
        result, slots = run(ENGINE, "I have a peach-coloured dress. What jewellery would look good with it? I have a dusky skin tone.")
        self.assertIn("neckline", result.reply.lower())
        self.assertIn("not fixed rules", result.reply.lower())
        self.assertIsNone(slots.colour)  # peach is the owned outfit, not a product colour filter
        result, slots = run(ENGINE, "It has a boat neckline", "budget 2000", slots=slots)
        self.assertTrue(result.products)
        for p in result.products:
            self.assertLessEqual(int(p["price_inr"]), 2000)
            self.assertIn(p["category"], ("Jewellery", "Accessories"))
        self.assertNotRegex(result.reply.lower(), r"\b(real|genuine|pure) gold")

    def test_p3_running_and_gym_asks_priority_then_size(self):
        result, slots = run(ENGINE, "Suggest good sports shoes for me. I need them for running and gym, ideally under ₹4,000.")
        self.assertIn("running", result.reply.lower())
        self.assertIn("gym", result.reply.lower())
        result, slots = run(ENGINE, "Running is the priority", slots=slots)
        self.assertIn("size", result.reply.lower())
        result, slots = run(ENGINE, "UK 6", slots=slots)
        self.assertTrue(result.products)
        for p in result.products:
            self.assertEqual(p["category"], "Footwear")
            self.assertNotIn("injur", result.reply.lower())

    def test_p4_cocktail_and_delivery_question_has_no_date(self):
        result, slots = run(ENGINE, "I have a cocktail party this weekend. I need something stylish under ₹3,000.", "M")
        self.assertTrue(result.products)
        result, _ = run(ENGINE, "will it arrive by Saturday?", slots=slots)
        self.assertNotRegex(result.reply, r"(?i)arrive[sd]? (by|on)|will be delivered|tomorrow")

    def test_p5_office_comfort(self):
        result, slots = run(ENGINE, "I need comfortable outfits for office and daily wear. My budget is ₹2,000 per outfit.", "size L")
        self.assertTrue(result.products)
        for p in result.products:
            self.assertLessEqual(int(p["price_inr"]), 2000)

    def test_p6_gift_jewellery_and_purity_question(self):
        result, slots = run(ENGINE, "I want jewellery for my mother's birthday. My budget is ₹2,500. What would you suggest?")
        self.assertTrue(result.products or "?" in result.reply)
        result, slots = run(ENGINE, "traditional", slots=slots)
        self.assertTrue(result.products)
        for p in result.products:
            self.assertLessEqual(int(p["price_inr"]), 2500)
        result, _ = run(ENGINE, "is it real gold?", slots=slots)
        self.assertNotRegex(result.reply.lower(), r"\b(it is|they are|made of|is) (real|pure|genuine|solid)\b")


class ProductQuestionTests(unittest.TestCase):
    def test_stock_question_names_the_product(self):
        result, _ = run(ENGINE, "Is the Ira Pastel Lehenga Set in stock?")
        self.assertEqual(ids(result), ["F003"])
        self.assertIn("Low stock", result.reply)

    def test_price_care_material(self):
        self.assertIn("₹899", run(ENGINE, "what is the price of Mira Antique Gold Jhumkas")[0].reply)
        self.assertIn("Dry clean", run(ENGINE, "how do I wash the Aarohi Peach Anarkali")[0].reply)
        self.assertIn("Cotton voile", run(ENGINE, "what material is Kiara Floral Maxi Dress")[0].reply)

    def test_unstocked_size_for_named_product(self):
        self.assertIn("not listed", run(ENGINE, "Do you have Naina Black Midi Dress in size XL?")[0].reply)

    def test_question_does_not_pollute_slots(self):
        _, slots = run(ENGINE, "how do I wash the Aarohi Peach Anarkali")
        self.assertIsNone(slots.colour)
        self.assertIsNone(slots.product_type)

    def test_buy_named_product_is_not_an_order(self):
        result, _ = run(ENGINE, "I want to buy Aura Minimal Analogue Watch")
        self.assertNotIn("order placed", result.reply.lower())
        self.assertIn("check out", result.reply.lower())
        self.assertNotIn("mock", result.reply.lower())
        self.assertNotIn("demo", result.reply.lower())

    def test_checkout_completes_without_keeping_details(self):
        engine = ENGINE
        watch = next(p for p in engine.products if "Aura Minimal" in p.product_name)
        slots = ShopperSlots()
        start = engine.handle_turn("t", f"I want to buy {watch.product_name}", slots)
        self.assertEqual(slots.checkout_step, "name")
        self.assertTrue(start.products)
        engine.handle_turn("t", "Riya Sharma", slots)
        self.assertEqual(slots.checkout_step, "address")
        engine.handle_turn("t", "Mumbai", slots)
        self.assertEqual(slots.checkout_step, "payment")
        titles = [item["title"] for item in engine.handle_turn("t", "UPI", slots).follow_ups]
        self.assertEqual(slots.checkout_step, "confirm")
        self.assertIn("Place order", titles)
        done = engine.handle_turn("t", "Place this order", slots)
        self.assertIn("order confirmed", done.reply.lower())
        self.assertIn(f"ord-{watch.product_id}".lower(), done.reply.lower())
        self.assertNotIn("mock", done.reply.lower())
        self.assertNotIn("demo", done.reply.lower())
        self.assertNotIn("riya", done.reply.lower())
        self.assertIsNotNone(done.confirmation)
        self.assertEqual(done.confirmation["reference"], f"ORD-{watch.product_id}")
        self.assertEqual(done.confirmation["name"], "Riya Sharma")
        self.assertEqual(done.confirmation["address"], "Mumbai")
        self.assertEqual(done.confirmation["payment"], "UPI")
        self.assertEqual(done.confirmation["product_id"], watch.product_id)
        self.assertIsNone(slots.checkout_step)
        self.assertIsNone(slots.checkout_name)
        self.assertIsNone(slots.checkout_address)
        self.assertIsNone(slots.checkout_payment)
        self.assertEqual(slots.intent, "shop")

    def test_checkout_asks_listed_size(self):
        engine = ENGINE
        clothing = next(
            p
            for p in engine.products
            if p.category in ("Ethnic wear", "Western wear")
            and "," in p.sizes_raw
            and "one size" not in p.sizes_raw.lower()
        )
        slots = ShopperSlots()
        result = engine.handle_turn("t", f"Checkout {clothing.product_name}", slots)
        self.assertEqual(slots.checkout_step, "size")
        self.assertIn("listed size", result.reply.lower())
        titles = [item["title"] for item in result.follow_ups]
        first_size = clothing.sizes_raw.split(",")[0].strip()
        self.assertTrue(any(first_size.upper() in title.upper() for title in titles))
        next_turn = engine.handle_turn("t", f"Size {first_size}", slots)
        self.assertEqual(slots.checkout_step, "name")
        self.assertEqual(slots.checkout_size.upper(), first_size.upper())
        self.assertIn("name", next_turn.reply.lower())

    def test_checkout_city_is_not_treated_as_delivery_faq(self):
        slots = ShopperSlots()
        ENGINE.handle_turn("t", "I want to buy Aura Minimal Analogue Watch", slots)
        ENGINE.handle_turn("t", "Riya Sharma", slots)
        result = ENGINE.handle_turn("t", "Mumbai", slots)
        self.assertEqual(slots.checkout_step, "payment")
        self.assertIn("pay", result.reply.lower())
        self.assertNotIn("pin code", result.reply.lower())
        titles = [item["title"] for item in result.follow_ups]
        self.assertIn("UPI", titles)
        self.assertIn("Cash on delivery", titles)

    def test_checkout_cancel_and_cheaper_abort(self):
        slots = ShopperSlots()
        ENGINE.handle_turn("t", "I want to buy Aura Minimal Analogue Watch", slots)
        cancelled = ENGINE.handle_turn("t", "Cancel checkout", slots)
        self.assertIsNone(slots.checkout_step)
        self.assertIn("cancelled", cancelled.reply.lower())
        ENGINE.handle_turn("t", "I want to buy Aura Minimal Analogue Watch", slots)
        ENGINE.handle_turn("t", "Show me cheaper options", slots)
        self.assertIsNone(slots.checkout_step)


class FAQTests(unittest.TestCase):
    def test_every_faq_question_matches_itself(self):
        for faq in ENGINE.faqs:
            self.assertEqual(match_faq(faq.question, ENGINE.faqs).question, faq.question)

    def test_faq_turn_keeps_slots(self):
        _, slots = run(ENGINE, "office wear under 2000", "M")
        before = (slots.occasion, slots.budget_max, slots.size)
        result, slots = run(ENGINE, "What is your return policy?", slots=slots)
        self.assertEqual((slots.occasion, slots.budget_max, slots.size), before)
        self.assertEqual(result.intent, "faq")

    def test_faq_without_question_mark_while_accessory_offer_pending(self):
        _, slots = run(ENGINE, "I have a cocktail party this weekend. I need something stylish under 3000", "M")
        result, slots = run(ENGINE, "what is your return policy", slots=slots)
        self.assertEqual(result.intent, "faq")
        self.assertEqual(result.products, [])
        result, slots = run(ENGINE, "will it arrive by Saturday?", slots=slots)
        self.assertNotIn("matching jewellery", result.reply.lower())  # offer is made only once
        self.assertEqual([f["title"] for f in result.follow_ups][:1], ["Yes, accessories"])
        result, slots = run(ENGINE, "yes please", slots=slots)
        self.assertTrue(all(p["category"] in ("Jewellery", "Accessories") for p in result.products))

    def test_greeting_mid_flow_resumes_question(self):
        _, slots = run(ENGINE, "office wear under 2000")
        result, _ = run(ENGINE, "hi", slots=slots)
        self.assertIn("size", result.reply.lower())

    def test_off_catalogue_declined(self):
        for msg in ("do you sell perfume?", "show me men's suits", "can you recommend a laptop"):
            result, _ = run(ENGINE, msg)
            self.assertEqual(result.products, [], msg)
            self.assertIn("catalogue", result.reply.lower())

    def test_greeting_and_empty(self):
        result, _ = run(ENGINE, "hi")
        self.assertEqual(result.products, [])
        result, _ = run(ENGINE, "   ")
        self.assertIn("looking for", result.reply)

    def test_very_long_input_does_not_crash(self):
        result, _ = run(ENGINE, "I want a dress for a wedding " * 500)
        self.assertTrue(result.reply)


class HandoffTests(unittest.TestCase):
    def test_single_complaint_does_not_handoff_second_does(self):
        result, slots = run(ENGINE, "this is useless")
        self.assertFalse(result.handoff)
        result, slots = run(ENGINE, "still not helping", slots=slots)
        self.assertTrue(result.handoff)
        result, slots = run(ENGINE, "show me casual outfits under 2000", slots=slots)
        self.assertIn("size", result.reply.lower())

    def test_explicit_human_request(self):
        result, _ = run(ENGINE, "I want to talk to a human")
        self.assertTrue(result.handoff)


class GuardAndFallbackTests(unittest.TestCase):
    def test_guards(self):
        prods = [{"product_id": "F001", "price_inr": 4999, "stock_status": "In stock", "name": "x"}]
        self.assertIsNotNone(violation("It will be delivered by Friday.", prods))
        self.assertIsNotNone(violation("These shoes help prevent injury.", prods))
        self.assertIsNotNone(violation("Priced at ₹1234 only.", prods))
        self.assertIsNotNone(violation("Real gold plated look", prods))
        self.assertTrue(has_markdown_table("| a | b |\n|---|---|\n| 1 | 2 |"))
        self.assertNotIn("**", strip_markdown("**bold** text"))

    def test_bad_llm_reply_falls_back_to_template(self):
        engine = RecommendationEngine(grok=FakeLLM(reply="Delivered tomorrow! Only ₹1. These shoes prevent injury."))
        result, _ = run(engine, "office wear under 2000", "M")
        self.assertTrue(result.products)
        self.assertNotIn("Delivered tomorrow", result.reply)
        self.assertNotIn("₹1.", result.reply)

    def test_markdown_table_reply_is_rejected(self):
        engine = RecommendationEngine(grok=FakeLLM(reply="| a | b |\n|---|---|\n| 1 | 2 |"))
        result, _ = run(engine, "office wear under 2000", "M")
        self.assertNotIn("|---|", result.reply)

    def test_llm_failures_fall_back_to_rules(self):
        engine = RecommendationEngine(grok=FakeLLM(fail_parse=True))
        result, _ = run(engine, "office wear under 2000", "M")
        self.assertTrue(result.products)

    def test_low_stock_added_when_llm_omits_it(self):
        engine = RecommendationEngine(grok=FakeLLM(reply="Ira Pastel Lehenga Set at ₹8999 suits a wedding."))
        result, _ = run(engine, "wedding lehenga under 9000 size M")
        self.assertIn("Low stock", result.reply)

    def test_cards_match_products_named_in_the_reply(self):
        engine = RecommendationEngine()
        slots = ShopperSlots()
        tia = next(p for p in engine.products if p.product_id == "J004")
        zoya = next(p for p in engine.products if p.product_id == "J016")
        nila = next(p for p in engine.products if p.product_id == "J013")
        payload = [engine._product_payload(p, slots) for p in (tia, nila, zoya)]
        result = engine._pack(
            "• Zoya Black Cord Disc Necklace – ₹649 – Size Adjustable – In stock.",
            slots,
            payload,
        )
        self.assertEqual(ids(result), ["J016"])
        self.assertEqual(result.products[0]["product_name"], "Zoya Black Cord Disc Necklace")
        result = engine._pack(
            "• Nila Silver Bar Pendant (J013)\n• Tia Rose Gold Minimal Chain (J004)",
            slots,
            payload,
        )
        self.assertEqual(ids(result), ["J013", "J004"])

    def test_llm_reply_that_names_one_shortlist_item_falls_back_to_all_cards(self):
        engine = RecommendationEngine(
            grok=FakeLLM(reply="• Zoya Black Cord Disc Necklace – ₹649. No other necklace matches.")
        )
        result, _ = run(
            engine,
            "I need an office necklace under 5000, gold colour, I prefer a minimal style",
        )
        self.assertTrue(result.products)
        for product in result.products:
            self.assertIn(product["product_name"], result.reply)
        self.assertGreaterEqual(len(result.products), 1)

    def test_llm_reasoning_is_not_used_as_reply(self):
        from src.grok_client import GrokClient

        self.assertFalse(hasattr(GrokClient, "_reasoning_as_reply"))


class SessionStoreTests(unittest.TestCase):
    def test_checkout_details_are_not_written_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            store = SessionStore(path)
            slots = store.get("c")
            slots.budget_max = 2000
            slots.checkout_step = "name"
            slots.checkout_product_id = "A003"
            slots.checkout_name = "Riya Sharma"
            slots.checkout_address = "Mumbai"
            slots.checkout_payment = "UPI"
            slots.last_question_asked = "What name should I put on this order?"
            slots.history = [
                "user: Riya Sharma",
                "assistant: Which city should I deliver to?",
            ]
            store.update("c", slots)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("Riya", raw)
            self.assertNotIn("Mumbai", raw)
            self.assertNotIn("UPI", raw)
            loaded = SessionStore(path).get("c")
            self.assertEqual(loaded.budget_max, 2000)
            self.assertIsNone(loaded.checkout_step)
            self.assertIsNone(loaded.checkout_name)
            self.assertIsNone(loaded.checkout_address)
            self.assertIsNone(loaded.checkout_payment)
            self.assertIsNone(loaded.last_question_asked)

    def test_persist_reload_and_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            store = SessionStore(path)
            slots = store.get("a")
            slots.budget_max = 1234
            store.update("a", slots)
            self.assertEqual(SessionStore(path).get("a").budget_max, 1234)
            store.reset("a")
            self.assertIsNone(SessionStore(path).get("a").budget_max)

    def test_corrupt_and_unknown_fields_do_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(SessionStore(path).get("x").budget_max)
            path.write_text(json.dumps({"a": {"budget_max": 5, "bogus_field": 1}, "b": "oops"}), encoding="utf-8")
            store = SessionStore(path)
            self.assertEqual(store.get("a").budget_max, 5)

    def test_concurrent_updates_keep_file_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            store = SessionStore(path)

            def worker(n):
                for i in range(15):
                    s = store.get("c%d" % n)
                    s.budget_max = i
                    store.update("c%d" % n, s)

            threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data), 8)

    def test_session_cap(self):
        import src.session as session

        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "s.json")
            old = session.MAX_SESSIONS
            session.MAX_SESSIONS = 5
            try:
                for i in range(12):
                    store.get("id%d" % i)
                self.assertLessEqual(len(store._cache), 5)
            finally:
                session.MAX_SESSIONS = old


class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        import src.web as web

        cls.web = web
        cls._tmp = tempfile.TemporaryDirectory()
        web.sessions = SessionStore(Path(cls._tmp.name) / "s.json")
        cls.client = TestClient(web.app)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_chat_roundtrip_and_reset(self):
        r = self.client.post("/api/chat", json={"message": "office wear under 2000", "session_id": "w1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["context"]["budget_max"], 2000)
        self.assertEqual(self.client.post("/api/reset", json={"session_id": "w1"}).json()["ok"], True)
        r = self.client.post("/api/chat", json={"message": "hi", "session_id": "w1"})
        self.assertIsNone(r.json()["context"]["budget_max"])

    def test_validation(self):
        self.assertEqual(self.client.post("/api/chat", json={"message": "x" * 1001, "session_id": "w2"}).status_code, 422)
        self.assertEqual(self.client.post("/api/chat", json={"message": "hi", "session_id": "../etc"}).status_code, 422)
        self.assertEqual(self.client.post("/api/chat", json={"message": "", "session_id": "w2"}).status_code, 422)

    def test_engine_error_is_a_clean_500(self):
        original = self.web.engine.handle_turn
        self.web.engine.handle_turn = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
        try:
            r = self.client.post("/api/chat", json={"message": "hi", "session_id": "w3"})
        finally:
            self.web.engine.handle_turn = original
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("Traceback", r.text)

    def test_sessions_are_isolated(self):
        self.client.post("/api/chat", json={"message": "office wear under 2000", "session_id": "iso1"})
        r = self.client.post("/api/chat", json={"message": "festive outfit under 6000", "session_id": "iso2"})
        self.assertEqual(r.json()["context"]["budget_max"], 6000)
        r = self.client.post("/api/chat", json={"message": "hello", "session_id": "iso1"})
        self.assertEqual(r.json()["context"]["budget_max"], 2000)

    def test_checkout_page_and_product_api(self):
        page = self.client.get("/checkout")
        self.assertEqual(page.status_code, 200)
        self.assertIn("checkout-form", page.text)
        product = self.client.get("/api/product/F001")
        self.assertEqual(product.status_code, 200)
        data = product.json()
        self.assertEqual(data["product_id"], "F001")
        self.assertIn("size_options", data)
        self.assertTrue(data.get("image_url"))
        missing = self.client.get("/api/product/NOPE")
        self.assertEqual(missing.status_code, 404)


class TelegramSplitTests(unittest.TestCase):
    def test_split_keeps_tags_intact(self):
        from src.telegram_bot import split_message

        text = "\n\n".join("<b>name</b> " + "é" * 900 for _ in range(8))
        chunks = split_message(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4000)
            self.assertEqual(chunk.count("<"), chunk.count(">"))
        self.assertEqual(split_message("short"), ["short"])


if __name__ == "__main__":
    unittest.main()


class StaleSlotLoopTests(unittest.TestCase):
    """The reported chat: gym stayed set after festive/casual, old raw slots, and a no-match loop."""

    CHAT = [
        "I need comfortable outfits for office and daily wear",
        "5000",
        "L",
        "I want to change the occasion",
        "festive",
        "1000",
        "10000",
        "I want to change the occasion",
        "It's for sports or gym",
        "XL",
        "I need an outfit for a festive occasion.",
        "10000",
        "I need casual everyday outfits.",
        "I want to change my budget",
        "My maximum budget is 10000 rupees",
    ]

    def _replay(self, engine):
        slots = ShopperSlots()
        replies = []
        for message in self.CHAT:
            replies.append((message, engine.handle_turn("t", message, slots)))
        return slots, replies

    def _check(self, slots, replies):
        by_msg = {}
        for message, result in replies:
            by_msg.setdefault(message, []).append(result)
        self.assertIn("budget", by_msg["1000"][0].reply.lower())          # honest no-match, names the budget
        self.assertIn("₹1000", by_msg["1000"][0].reply)
        self.assertTrue(by_msg["10000"][0].products)                       # bare "10000" after a no-match is a budget
        gym = by_msg["It's for sports or gym"][0]
        self.assertTrue(gym.products)
        self.assertTrue(all(p["category"] in ("Ethnic wear", "Western wear") for p in gym.products))  # activewear, not shoes
        self.assertTrue({p["product_id"] for p in by_msg["XL"][0].products} <= {"F015", "F016", "F039", "F043"})
        self.assertTrue(by_msg["XL"][0].products)
        festive = by_msg["I need an outfit for a festive occasion."][0]
        self.assertTrue(festive.products)                                  # gym no longer ANDed with festive
        casual = by_msg["I need casual everyday outfits."][0]
        self.assertTrue(casual.products)
        self.assertEqual(slots.occasion, "casual")
        self.assertIsNone(slots.activity)
        self.assertEqual(slots.budget_max, 10000)
        self.assertEqual(slots.size, "XL")
        for message, result in replies:
            if message not in ("1000",) and "change" not in message:
                self.assertNotIn("occasion or activity", result.reply)
        self.assertTrue(replies[-1][1].products)

    def test_exact_chat_without_llm(self):
        self._check(*self._replay(ENGINE))

    def test_exact_chat_with_llm_returning_raw_values(self):
        class Raw(FakeLLM):
            def parse_message(self, message, context):
                return {"category": "clothing", "product_type": "outfit", "occasion": "sports" if "gym" in message else None,
                        "activity": "gym" if "gym" in message else None}

        self._check(*self._replay(RecommendationEngine(grok=Raw())))

    def test_slots_loaded_from_old_session_are_canonicalised(self):
        slots = ShopperSlots(category="clothing", product_type="outfit", occasion="casual", activity="gym",
                             budget_max=10000, size="XL", style="casual")
        slots.canonicalise()
        self.assertIsNone(slots.category)
        self.assertIsNone(slots.product_type)
        self.assertEqual(slots.scope, "clothing")
        self.assertEqual(slots.size, "XL")
        result = ENGINE.handle_turn("t", "I need casual everyday outfits.", slots)
        self.assertTrue(result.products)
        self.assertIsNone(slots.activity)

    def test_session_store_canonicalises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps({"old": {"category": "clothing", "product_type": "outfit", "size": "M or L", "budget_max": "5000"}}), encoding="utf-8")
            slots = SessionStore(path).get("old")
            self.assertIsNone(slots.category)
            self.assertIsNone(slots.product_type)
            self.assertEqual(slots.size, "M, L")
            self.assertEqual(slots.budget_max, 5000)

    def test_canonicalise_is_idempotent(self):
        slots = ShopperSlots(category="Ethnic wear", product_type="kurta", occasion="office, daily", activity="running gym",
                             colour="peach, pastel", size="M, L", style="casual", budget_max=3000)
        before = (slots.category, slots.product_type, slots.occasion, slots.activity, slots.colour, slots.size, slots.style)
        slots.canonicalise()
        self.assertEqual(before, (slots.category, slots.product_type, slots.occasion, slots.activity, slots.colour, slots.size, slots.style))

    def test_occasion_activity_conflict_is_named_with_a_way_out(self):
        slots = ShopperSlots(occasion="festive", activity="gym", budget_max=10000, size="XL", scope="clothing")
        result = ENGINE.handle_turn("t", "show me options", slots)
        self.assertEqual(result.products, [])
        self.assertIn("festive", result.reply)
        self.assertIn("gym", result.reply)
        self.assertIn("Keep gym", [c["title"] for c in result.follow_ups])
        result = ENGINE.handle_turn("t", "Drop the activity filter", slots)
        self.assertTrue(result.products)
        self.assertIsNone(slots.activity)
        self.assertEqual(slots.occasion, "festive")

    def test_repeated_no_match_names_the_blocker_and_budget_answer_unblocks(self):
        result, slots = run(ENGINE, "festive outfit under 1000", "L")
        self.assertEqual(result.products, [])
        result, slots = run(ENGINE, "I want to change my size", "M", slots=slots)
        self.assertEqual(result.products, [])
        self.assertIn("blocker is the budget", result.reply)   # not a generic "change a requirement" loop
        result, slots = run(ENGINE, "10000", slots=slots)
        self.assertTrue(result.products)
        self.assertEqual(slots.budget_max, 10000)

    def test_no_match_names_the_failing_value_for_activity(self):
        slots2 = ShopperSlots(activity="gym", budget_max=10000, size="M", colour="red", scope="clothing")
        result = ENGINE.handle_turn("t", "show me options", slots2)
        self.assertIn("colour", result.reply.lower())
        self.assertIn("red", result.reply)

    def test_new_occasion_replaces_old_activity_and_new_activity_replaces_occasion(self):
        _, slots = run(ENGINE, "It's for gym", "festive")
        self.assertEqual(slots.occasion, "festive")
        self.assertIsNone(slots.activity)
        _, slots = run(ENGINE, "festive outfit under 8000", "M", "I need an outfit for sports or gym")
        self.assertIsNone(slots.occasion)
        self.assertIn("gym", slots.activity)

    def test_generic_outfit_request_after_shoes_resets_type_and_size(self):
        _, slots = run(ENGINE, "sandals under 1500", "UK 6")
        result, slots = run(ENGINE, "I need casual everyday outfits under 2000", "M", slots=slots)
        self.assertIsNone(slots.product_type)
        self.assertEqual(slots.size, "M")
        self.assertTrue(result.products)
        self.assertTrue(all(p["category"] != "Footwear" for p in result.products))

    def test_wrong_kind_of_size_is_dropped_when_the_search_changes(self):
        _, slots = run(ENGINE, "running shoes under 4000", "UK 6")
        result, slots = run(ENGINE, "show me casual kurtas under 2000", slots=slots)
        self.assertNotEqual(slots.size, "UK 6")
        self.assertIn("size", result.reply.lower())

    def test_bare_size_updates_a_running_clothing_search(self):
        _, slots = run(ENGINE, "office wear under 2000", "M")
        result, slots = run(ENGINE, "XL", slots=slots)
        self.assertEqual(slots.size, "XL")
        self.assertTrue(result.products)

    def test_activity_request_for_outfits_is_clothing_only(self):
        result, _ = run(ENGINE, "I need an outfit for gym under 3000", "M")
        self.assertTrue(result.products)
        self.assertTrue(all(p["category"] != "Footwear" for p in result.products))
        result, _ = run(ENGINE, "I need gym shoes under 4000", "UK 6")
        self.assertTrue(all(p["category"] == "Footwear" for p in result.products))
