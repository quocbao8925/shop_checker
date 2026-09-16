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
KINGDOM_CURRENCY_ID = "85ca954a-41f2-ce94-9b45-8ca3dd39a00d"
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
            kingdom_credits=balances.get(KINGDOM_CURRENCY_ID, 0),
        )

    def parse_daily_store(self, raw_storefront: dict[str, Any]) -> DailyStore:
        """Parse and resolve daily weapon offers against the local asset cache."""
        panel = raw_storefront.get("SkinsPanelLayout", {})
        raw_offers = panel.get("SingleItemStoreOffers") or panel.get("SingleItemOffers", [])
        seconds_remaining = panel.get("SingleItemOffersRemainingDurationInSeconds", 0)

        offers: list[SkinOffer] = []
        for raw_offer in raw_offers:
            if isinstance(raw_offer, str):
                raw_offer = {"OfferID": raw_offer}
            if not isinstance(raw_offer, dict):
                continue
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
        raw_bundles = featured.get("Bundles") or ([featured["Bundle"]] if featured.get("Bundle") else [])

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

            raw_items = raw_bundle.get("Items") or []
            if not raw_items:
                for item_offer in raw_bundle.get("ItemOffers") or []:
                    offer = item_offer.get("Offer") or {}
                    for reward in offer.get("Rewards") or []:
                        raw_items.append({
                            "Item": reward,
                            "BasePrice": (offer.get("Cost") or {}).get(VP_CURRENCY_ID, 0),
                            "DiscountedPrice": (item_offer.get("DiscountedCost") or offer.get("Cost") or {}).get(VP_CURRENCY_ID, 0),
                            "DiscountPercent": item_offer.get("DiscountPercent", 0),
                        })
            for raw_item in raw_items:
                item_uuid = raw_item.get("Item", {}).get("ItemID", "")
                base_price = raw_item.get("BasePrice", 0)
                discounted_price = raw_item.get("DiscountedPrice", base_price)
                discount_pct = raw_item.get("DiscountPercent", 0.0)

                skin = self.cache.get_item(item_uuid)
                item_name = (skin.get("display_name") if skin else None) or raw_item.get("DisplayName") or f"Item {item_uuid[:8]}"
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

            total_base = (raw_bundle.get("TotalBaseCost") or {}).get(VP_CURRENCY_ID, total_base)
            total_discounted = (raw_bundle.get("TotalDiscountedCost") or {}).get(VP_CURRENCY_ID, total_discounted)
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
            sections=self.parse_sections(raw_storefront),
        )
        self.cache.save_store_snapshot(snapshot)
        return snapshot


    def _price_label(self, costs: dict) -> str:
        labels = {VP_CURRENCY_ID: "VP", KINGDOM_CURRENCY_ID: "KC", RADIANITE_CURRENCY_ID: "RP"}
        parts = []
        for currency, amount in costs.items():
            metadata = self.cache.get_item(currency) or {}
            unit = labels.get(currency, metadata.get("display_name", "currency"))
            parts.append(f"{amount:,} {unit}")
        return " + ".join(parts) if parts else ""

    def parse_sections(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Include optional storefront sections, never inventing absent offers."""
        definitions = (
            ("AccessoryStore", "ACCESSORIES", "AccessoryStoreOffers", "AccessoryStoreRemainingDurationInSeconds"),
            ("BonusStore", "NIGHT MARKET", "BonusStoreOffers", "BonusStoreRemainingDurationInSeconds"),
            ("UpgradeCurrencyStore", "RADIANITE POINTS", "UpgradeCurrencyOffers", None),
        )
        sections = []
        for key, title, offers_key, timer_key in definitions:
            if key not in raw or not isinstance(raw[key], dict):
                continue
            panel = raw[key]
            items = []
            for wrapper in panel.get(offers_key) or []:
                offer = wrapper.get("Offer") or wrapper
                costs = wrapper.get("DiscountCosts")
                if costs is None:
                    costs = wrapper.get("DiscountedCost")
                if costs is None:
                    costs = offer.get("Cost") or {}
                rewards = offer.get("Rewards") or []
                # A price belongs to an offer, not to each reward separately.
                resolved = []
                for reward in rewards:
                    uuid = reward.get("ItemID", "")
                    metadata = self.cache.get_item(uuid) or {}
                    resolved.append({
                        "name": metadata.get("display_name") or reward.get("DisplayName") or f"Item {uuid[:8]}",
                        "display_icon": metadata.get("display_icon") or "",
                        "kind": metadata.get("kind", ""),
                        "quantity": reward.get("Quantity", 1),
                    })
                if not resolved:
                    continue
                item = resolved[0]
                if len(resolved) > 1:
                    item = {**item, "name": " + ".join(r["name"] for r in resolved)}
                elif item["quantity"] > 1:
                    item = {**item, "name": f'{item["quantity"]} x {item["name"]}'}
                items.append({
                    **item, "price_label": self._price_label(costs),
                    "discount_percent": wrapper.get("DiscountPercent", 0),
                })
            sections.append({
                "name": title, "items": items,
                "seconds_remaining": panel.get(timer_key) if timer_key else None,
            })
        return sections
