"""Unit tests for main_project core logic and modules."""

import tempfile
import unittest
from unittest.mock import MagicMock, patch

from api.store_client import StoreClient
from auth.riot_auth import AuthenticationError, RiotAuthService
from auth.secure_store import SecureTokenStore
from cache.db import DatabaseCache
from models import AuthTokens, ContentTier, DailyStore, SkinOffer, StoreSnapshot, Wallet


class TestModels(unittest.TestCase):
    def test_auth_tokens_serialization(self):
        tokens = AuthTokens(
            access_token="test_access",
            id_token="test_id",
            entitlements_token="test_ent",
            puuid="test_puuid",
            region="ap",
            shard="ap",
            created_at=1000.0,
            expires_in=10800,
        )
        d = tokens.to_dict()
        self.assertEqual(d["access_token"], "test_access")
        self.assertEqual(d["shard"], "ap")

        reconstructed = AuthTokens.from_dict(d)
        self.assertEqual(reconstructed.access_token, tokens.access_token)
        self.assertEqual(reconstructed.shard, "ap")

    def test_skin_offer_serialization(self):
        offer = SkinOffer(
            uuid="skin-123",
            name="Prime Vandal",
            display_icon="https://example.com/icon.png",
            content_tier_uuid="tier-exclusive",
            content_tier_name="Exclusive",
            content_tier_color="f0b232",
            cost=1775,
        )
        d = offer.to_dict()
        reconstructed = SkinOffer.from_dict(d)
        self.assertEqual(reconstructed.name, "Prime Vandal")
        self.assertEqual(reconstructed.cost, 1775)


class TestRiotAuth(unittest.TestCase):
    def test_extract_tokens_from_full_url(self):
        url = (
            "http://localhost/redirect#access_token=eyJh...&id_token=eyJh.id..."
            "&token_type=Bearer&expires_in=3600"
        )
        extracted = RiotAuthService.extract_tokens(url)
        self.assertEqual(extracted["access_token"], "eyJh...")
        self.assertEqual(extracted["id_token"], "eyJh.id...")
        self.assertEqual(extracted["expires_in"], "3600")

    def test_extract_tokens_from_fragment(self):
        fragment = "access_token=token123&id_token=id456"
        extracted = RiotAuthService.extract_tokens(fragment)
        self.assertEqual(extracted["access_token"], "token123")
        self.assertEqual(extracted["id_token"], "id456")

    def test_extract_tokens_invalid(self):
        with self.assertRaises(AuthenticationError):
            RiotAuthService.extract_tokens("http://localhost/redirect#no_token_here")


class TestSecureStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store = SecureTokenStore(storage_dir=self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_load_clear(self):
        tokens = AuthTokens(
            access_token="tok1",
            id_token="id1",
            entitlements_token="ent1",
            puuid="puuid1",
            region="na",
            shard="na",
        )
        self.store.save_tokens(tokens)
        loaded = self.store.load_tokens()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.access_token, "tok1")

        self.store.clear_tokens()
        self.assertIsNone(self.store.load_tokens())


class TestDatabaseCache(unittest.TestCase):
    def setUp(self):
        self.cache = DatabaseCache(":memory:")

    def tearDown(self):
        self.cache.close()

    def test_asset_caching_and_resolution(self):
        skins_data = [
            {
                "uuid": "skin-parent-1",
                "displayName": "Reaver Vandal",
                "displayIcon": "https://example.com/reaver.png",
                "contentTierUuid": "tier-premium",
                "levels": [
                    {"uuid": "level-child-1"},
                    {"uuid": "level-child-2"},
                ],
            }
        ]
        tiers_data = [
            {
                "uuid": "tier-premium",
                "devName": "Premium Edition",
                "highlightColor": "d1548d",
                "displayIcon": "https://example.com/tier.png",
            }
        ]
        bundles_data = [
            {
                "uuid": "bundle-1",
                "displayName": "Reaver Collection",
                "displayIcon": "https://example.com/bundle.png",
                "description": "Reaver weapons bundle",
            }
        ]

        self.cache.save_assets(
            skins_data=skins_data,
            tiers_data=tiers_data,
            bundles_data=bundles_data,
            client_version="release-09.05",
        )

        self.assertTrue(self.cache.has_assets())
        self.assertEqual(self.cache.get_client_version(), "release-09.05")

        # Lookup by parent skin UUID
        skin = self.cache.get_skin("skin-parent-1")
        self.assertIsNotNone(skin)
        self.assertEqual(skin["display_name"], "Reaver Vandal")

        # Lookup by skin level UUID (reverse map)
        level_skin = self.cache.get_skin("level-child-2")
        self.assertIsNotNone(level_skin)
        self.assertEqual(level_skin["display_name"], "Reaver Vandal")

        # Lookup content tier
        tier = self.cache.get_content_tier("tier-premium")
        self.assertIsNotNone(tier)
        self.assertEqual(tier.highlight_color, "d1548d")

        # Lookup bundle
        bundle = self.cache.get_bundle("bundle-1")
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle["display_name"], "Reaver Collection")

    def test_store_snapshot_caching(self):
        snapshot = StoreSnapshot(
            daily_store=DailyStore(offers=[], seconds_remaining=3600),
            bundles=[],
            wallet=Wallet(valorant_points=2500, radianite_points=120),
        )
        self.cache.save_store_snapshot(snapshot)
        cached = self.cache.get_store_snapshot()
        self.assertIsNotNone(cached)
        self.assertEqual(cached.wallet.valorant_points, 2500)
        self.assertEqual(cached.daily_store.seconds_remaining, 3600)


class TestStoreClient(unittest.TestCase):
    def setUp(self):
        self.cache = DatabaseCache(":memory:")
        self.cache.save_assets(
            skins_data=[
                {
                    "uuid": "parent-vandal",
                    "displayName": "Glitchpop Vandal",
                    "displayIcon": "https://example.com/glitchpop.png",
                    "contentTierUuid": "tier-exclusive",
                    "levels": [{"uuid": "level-vandal-offer"}],
                }
            ],
            tiers_data=[
                {
                    "uuid": "tier-exclusive",
                    "devName": "Exclusive Edition",
                    "highlightColor": "f0b232",
                    "displayIcon": "",
                }
            ],
            bundles_data=[],
            client_version="test-version",
        )
        self.client = StoreClient(cache=self.cache)

    def tearDown(self):
        self.cache.close()

    def test_parse_daily_store(self):
        raw_storefront = {
            "SkinsPanelLayout": {
                "SingleItemStoreOffers": [
                    {
                        "OfferID": "level-vandal-offer",
                        "Cost": {"85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741": 2175},
                        "Rewards": [{"ItemID": "level-vandal-offer"}],
                    }
                ],
                "SingleItemOffersRemainingDurationInSeconds": 45000,
            }
        }
        daily_store = self.client.parse_daily_store(raw_storefront)
        self.assertEqual(daily_store.seconds_remaining, 45000)
        self.assertEqual(len(daily_store.offers), 1)
        offer = daily_store.offers[0]
        self.assertEqual(offer.name, "Glitchpop Vandal")
        self.assertEqual(offer.cost, 2175)
        self.assertEqual(offer.content_tier_color, "f0b232")


class TestValorantShopManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp_dir.cleanup()

    @patch("manager.RiotAuthService")
    def test_manager_auth_and_offline_flow(self, mock_auth_cls):
        mock_auth = MagicMock()
        mock_auth.authenticate_from_url.return_value = AuthTokens(
            access_token="mgr_tok",
            id_token="mgr_id",
            entitlements_token="mgr_ent",
            puuid="mgr_puuid",
            region="na",
            shard="na",
        )
        mock_auth.get_auth_url.return_value = "https://auth.riotgames.com/mock"
        mock_auth_cls.return_value = mock_auth

        from manager import ValorantShopManager

        manager = ValorantShopManager(storage_dir=self.tmp_dir.name)
        self.assertFalse(manager.is_authenticated)
        self.assertEqual(manager.get_login_url(), "https://auth.riotgames.com/mock")

        tokens = manager.login_with_url("http://localhost/redirect#access_token=mgr_tok")
        self.assertTrue(manager.is_authenticated)
        self.assertEqual(tokens.access_token, "mgr_tok")

        # Test logout
        manager.logout()
        self.assertFalse(manager.is_authenticated)
        manager.close()


if __name__ == "__main__":
    unittest.main()

