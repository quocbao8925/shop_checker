"""Riot Storefront and Wallet API Client.

Directly queries Riot PD servers to retrieve personal daily weapon offers,
featured bundles, and account wallet balances.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from cache.db import DatabaseCache
from models import (
    AuthTokens,
    Bundle,
    BundleItem,
    DailyStore,
    SkinOffer,
    StoreSnapshot,
    Wallet,
)

logger = logging.getLogger(__name__)

VP_CURRENCY_ID = "85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"
RADIANITE_CURRENCY_ID = "e59aa87c-4cbf-517a-5983-6e81511be9b7"

CLIENT_PLATFORM = (
    "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0"
    "Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0"
    "IjogIlVua25vd24iDQp9"
)


class StoreApiError(Exception):
    """Raised when Riot store endpoints return an error response."""


class StoreClient:
    def __init__(self, cache: DatabaseCache, timeout: float = 30.0) -> None:
        self.cache = cache
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self, tokens: AuthTokens, client_version: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {tokens.access_token}",
            "X-Riot-Entitlements-JWT": tokens.entitlements_token,
            "X-Riot-ClientPlatform": CLIENT_PLATFORM,
            "X-Riot-ClientVersion": client_version,
            "Content-Type": "application/json",
        }

    def fetch_raw_storefront(
        self, tokens: AuthTokens, client_version: str
    ) -> dict[str, Any]:
        """Query Riot storefront endpoint for raw JSON payload."""
        url = f"https://pd.{tokens.shard}.a.pvp.net/store/v3/storefront/{tokens.puuid}"
        headers = self._headers(tokens, client_version)
        try:
            resp = self.session.post(url, headers=headers, json={}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise StoreApiError(f"Network error querying storefront: {exc}") from exc

        if not resp.ok:
            raise StoreApiError(
                f"Storefront request failed (HTTP {resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    def fetch_wallet(self, tokens: AuthTokens, client_version: str) -> Wallet:
        """Fetch current VP and Radianite point balances."""
        url = f"https://pd.{tokens.shard}.a.pvp.net/store/v1/wallet/{tokens.puuid}"
        headers = self._headers(tokens, client_version)
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise StoreApiError(f"Network error querying wallet: {exc}") from exc

        if not resp.ok:
            raise StoreApiError(
                f"Wallet request failed (HTTP {resp.status_code}): {resp.text[:300]}"
            )

        data = resp.json()
        balances = data.get("Balances", {})
        return Wallet(
            valorant_points=balances.get(VP_CURRENCY_ID, 0),
            radianite_points=balances.get(RADIANITE_CURRENCY_ID, 0),
        )

    def parse_daily_store(self, raw_storefront: dict[str, Any]) -> DailyStore:
        """Parse and resolve daily weapon offers against the local asset cache."""
        panel = raw_storefront.get("SkinsPanelLayout", {})
        raw_offers = panel.get("SingleItemStoreOffers", [])
        seconds_remaining = panel.get("SingleItemOffersRemainingDurationInSeconds", 0)

        offers: list[SkinOffer] = []
        for raw_offer in raw_offers:
            offer_id = raw_offer.get("OfferID", "")
            cost = raw_offer.get("Cost", {}).get(VP_CURRENCY_ID, 0)

            # Check Rewards list for item UUID
            item_uuid = offer_id
            rewards = raw_offer.get("Rewards", [])
            if rewards and rewards[0].get("ItemID"):
                item_uuid = rewards[0]["ItemID"]

            # Resolve skin details from cache
            skin = self.cache.get_skin(item_uuid) or self.cache.get_skin(offer_id)
            if skin:
                tier_uuid = skin.get("content_tier_uuid", "")
                tier = self.cache.get_content_tier(tier_uuid) if tier_uuid else None
                offers.append(
                    SkinOffer(
                        uuid=skin["uuid"],
                        name=skin.get("display_name", "Unknown Skin"),
                        display_icon=skin.get("display_icon", ""),
                        content_tier_uuid=tier_uuid,
                        content_tier_name=tier.name if tier else "Standard",
                        content_tier_color=tier.highlight_color if tier else "",
                        cost=cost,
                    )
                )
            else:
                logger.warning("Skin UUID not found in cache: %s (offer %s)", item_uuid, offer_id)
                offers.append(
                    SkinOffer(
                        uuid=offer_id,
                        name="Unknown Skin",
                        display_icon="",
                        content_tier_uuid="",
                        content_tier_name="Unknown",
                        content_tier_color="",
                        cost=cost,
                    )
                )

        return DailyStore(offers=offers, seconds_remaining=seconds_remaining)

    def parse_bundles(self, raw_storefront: dict[str, Any]) -> list[Bundle]:
        """Parse and resolve featured bundles against the local asset cache."""
        featured = raw_storefront.get("FeaturedBundle", {})
        raw_bundles = featured.get("Bundles", [])

        bundles: list[Bundle] = []
        for raw_bundle in raw_bundles:
            bundle_uuid = raw_bundle.get("DataAssetID", "")
            bundle_info = self.cache.get_bundle(bundle_uuid)
            bundle_name = bundle_info["display_name"] if bundle_info else "Featured Bundle"
            bundle_icon = bundle_info.get("display_icon") if bundle_info else None
            duration = raw_bundle.get("DurationRemainingInSeconds", 0)

            items: list[BundleItem] = []
            total_base = 0
            total_discounted = 0

            for raw_item in raw_bundle.get("Items", []):
                item_uuid = raw_item.get("Item", {}).get("ItemID", "")
                base_price = raw_item.get("BasePrice", 0)
                discounted_price = raw_item.get("DiscountedPrice", base_price)
                discount_pct = raw_item.get("DiscountPercent", 0.0)

                skin = self.cache.get_skin(item_uuid)
                item_name = skin.get("display_name", "Unknown Item") if skin else "Unknown Item"
                item_icon = skin.get("display_icon", "") if skin else ""

                items.append(
                    BundleItem(
                        uuid=item_uuid,
                        name=item_name,
                        display_icon=item_icon,
                        base_price=base_price,
                        discounted_price=discounted_price,
                        discount_percent=discount_pct,
                    )
                )
                total_base += base_price
                total_discounted += discounted_price

            bundles.append(
                Bundle(
                    uuid=bundle_uuid,
                    name=bundle_name,
                    display_icon=bundle_icon,
                    items=items,
                    total_base_price=total_base,
                    total_discounted_price=total_discounted,
                    duration_remaining_secs=duration,
                )
            )

        return bundles

    def fetch_full_snapshot(
        self, tokens: AuthTokens, client_version: str
    ) -> StoreSnapshot:
        """Fetch storefront and wallet concurrently/sequentially and cache the result."""
        raw_storefront = self.fetch_raw_storefront(tokens, client_version)
        daily_store = self.parse_daily_store(raw_storefront)
        bundles = self.parse_bundles(raw_storefront)
        wallet = self.fetch_wallet(tokens, client_version)

        snapshot = StoreSnapshot(
            daily_store=daily_store,
            bundles=bundles,
            wallet=wallet,
        )
        self.cache.save_store_snapshot(snapshot)
        return snapshot
