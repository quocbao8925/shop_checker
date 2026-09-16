import unittest
from unittest.mock import Mock

from api.store_client import StoreClient, VP_CURRENCY_ID, KINGDOM_CURRENCY_ID
from api.valorant_api import ValorantApiClient
from cache.db import DatabaseCache
from models import StoreSnapshot, Wallet, DailyStore


class StoreSectionsTests(unittest.TestCase):
    def setUp(self):
        self.cache = DatabaseCache()
        self.client = StoreClient(self.cache)
        self.cache.save_assets(
            [{"uuid": "skin", "displayName": "Test Vandal", "displayIcon": "https://example.test/skin.png",
              "levels": [{"uuid": "level"}]}], [],
            [{"uuid": "bundle", "displayName": "Run It Back", "displayIcon": ""}], "test-version")
        self.cache.save_catalog_items([
            dict(uuid="card", display_name="Dog Days Card", display_icon="", kind="Player card"),
            dict(uuid="buddy-level", display_name="Buddy", display_icon="https://example.test/buddy.png", kind="Gun buddy"),
        ])

    def tearDown(self):
        self.client.session.close()
        self.cache.close()

    @staticmethod
    def offer(item, amount, currency=VP_CURRENCY_ID):
        return {"OfferID": "offer-" + item, "Cost": {currency: amount},
                "Rewards": [{"ItemID": item, "Quantity": 1}]}

    def test_bundle_skin_and_accessory_resolution_and_authoritative_total(self):
        bundle = self.client.parse_bundles({"FeaturedBundle": {"Bundles": [{
            "DataAssetID": "bundle",
            "Items": [
                {"Item": {"ItemID": "level"}, "BasePrice": 1775, "DiscountedPrice": 1200},
                {"Item": {"ItemID": "card"}, "BasePrice": 375, "DiscountedPrice": 0},
            ],
            "TotalDiscountedCost": {VP_CURRENCY_ID: 1000},
        }]}})[0]
        self.assertEqual(bundle.name, "Run It Back")
        self.assertEqual(bundle.total_discounted_price, 1000)
        self.assertEqual(bundle.items[0].name, "Test Vandal")
        self.assertTrue(bundle.items[0].display_icon)
        self.assertEqual(bundle.items[1].name, "Dog Days Card")
        self.assertEqual(bundle.items[1].display_icon, "")

    def test_itemoffers_fallback_and_single_bundle(self):
        bundle = self.client.parse_bundles({"FeaturedBundle": {"Bundle": {
            "DataAssetID": "bundle", "Items": [],
            "ItemOffers": [{"Offer": self.offer("level", 1775),
                            "DiscountedCost": {VP_CURRENCY_ID: 1100}}],
        }}})[0]
        self.assertEqual(bundle.items[0].name, "Test Vandal")
        self.assertEqual(bundle.total_discounted_price, 1100)

    def test_accessories_use_kingdom_credits_and_keep_images(self):
        sections = self.client.parse_sections({"AccessoryStore": {
            "AccessoryStoreRemainingDurationInSeconds": 100,
            "AccessoryStoreOffers": [{"Offer": self.offer("buddy-level", 4500, KINGDOM_CURRENCY_ID)}],
        }})
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["seconds_remaining"], 100)
        item = sections[0]["items"][0]
        self.assertEqual(item["price_label"], "4,500 KC")
        self.assertEqual(item["name"], "Buddy")
        self.assertTrue(item["display_icon"])

    def test_night_market_uses_discounted_price_including_zero(self):
        for price in [900, 0]:
            sections = self.client.parse_sections({"BonusStore": {"BonusStoreOffers": [{
                "Offer": self.offer("level", 1775), "DiscountPercent": 40,
                "DiscountCosts": {VP_CURRENCY_ID: price},
            }]}})
            item = sections[0]["items"][0]
            self.assertEqual(item["price_label"], f"{price} VP")
            self.assertEqual(item["discount_percent"], 40)
        self.assertEqual(self.client.parse_sections({}), [])

    def test_multiple_reward_offer_does_not_duplicate_price(self):
        offer = self.offer("level", 1500)
        offer["Rewards"].append({"ItemID": "card", "Quantity": 1})
        items = self.client.parse_sections({"AccessoryStore": {
            "AccessoryStoreOffers": [{"Offer": offer}],
        }})[0]["items"]
        self.assertEqual(len(items), 1)
        self.assertIn("Dog Days Card", items[0]["name"])
        self.assertEqual(items[0]["price_label"], "1,500 VP")

    def test_unknown_artwork_and_currency_do_not_invent_vp_or_image(self):
        items = self.client.parse_sections({"AccessoryStore": {"AccessoryStoreOffers": [{
            "Offer": self.offer("unknown-id", 10, "unknown-currency"),
        }]}})[0]["items"]
        self.assertEqual(items[0]["display_icon"], "")
        self.assertEqual(items[0]["price_label"], "10 currency")

    def test_old_snapshot_and_new_sections_roundtrip(self):
        original = StoreSnapshot(DailyStore([], 100), [], Wallet(10, 20))
        old = original.to_dict()
        old.pop("sections")
        old["wallet"].pop("kingdom_credits")
        self.assertEqual(StoreSnapshot.from_dict(old).sections, [])
        self.assertEqual(StoreSnapshot.from_dict(old).wallet.kingdom_credits, 0)
        original.sections = [{"name": "ACCESSORIES", "items": []}]
        original.wallet.kingdom_credits = 3000
        self.cache.save_store_snapshot(original)
        restored = self.cache.get_store_snapshot()
        self.assertEqual(restored.sections, original.sections)
        self.assertEqual(restored.wallet.kingdom_credits, 3000)

    def test_catalog_level_alias_title_without_image_and_ttl(self):
        api = ValorantApiClient()
        api.session.close()
        api.session = Mock()
        response = Mock()
        response.json.return_value = {"data": [{
            "uuid": "parent", "displayName": "Test buddy",
            "displayIcon": "https://example.test/icon.png", "levels": [{"uuid": "alias"}],
        }]}
        api.session.get.return_value = response
        api.sync_accessories(self.cache)
        self.assertEqual(self.cache.get_item("alias")["display_name"], "Test buddy")
        self.assertEqual(api.session.get.call_count, 5)
        api.sync_accessories(self.cache)
        self.assertEqual(api.session.get.call_count, 5)

    def test_failed_catalog_keeps_existing_data_and_retries_later(self):
        api = ValorantApiClient()
        api.session.close()
        api.session = Mock()
        api.session.get.side_effect = OSError("offline")
        api.sync_accessories(self.cache)
        self.assertEqual(self.cache.get_item("card")["display_name"], "Dog Days Card")
        self.assertEqual(self.cache.get_metadata("catalog_synced_playercards"), "")

    def test_daily_string_uuid_payload(self):
        daily = self.client.parse_daily_store({"SkinsPanelLayout": {"SingleItemOffers": ["level"]}})
        self.assertEqual(daily.offers[0].name, "Test Vandal")


if __name__ == "__main__":
    unittest.main()
