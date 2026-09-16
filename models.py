"""Data models for Valorant Shop Android Tool.

Uses standard library dataclasses for lightweight, on-device execution
without heavy external dependencies.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AuthTokens:
    access_token: str
    id_token: str
    entitlements_token: str
    puuid: str
    region: str
    shard: str
    created_at: float = field(default_factory=time.time)
    expires_in: int = 10800  # Default 3 hours token lifespan

    @property
    def is_expired(self) -> bool:
        """Check if the access token has expired."""
        return (time.time() - self.created_at) >= self.expires_in

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthTokens:
        return cls(
            access_token=data["access_token"],
            id_token=data.get("id_token", ""),
            entitlements_token=data.get("entitlements_token", ""),
            puuid=data.get("puuid", ""),
            region=data.get("region", "na"),
            shard=data.get("shard", "na"),
            created_at=data.get("created_at", time.time()),
            expires_in=data.get("expires_in", 10800),
        )


@dataclass
class ContentTier:
    uuid: str
    name: str
    display_icon: str
    highlight_color: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentTier:
        return cls(
            uuid=data["uuid"],
            name=data.get("name", "Unknown"),
            display_icon=data.get("display_icon", ""),
            highlight_color=data.get("highlight_color", ""),
        )


@dataclass
class SkinOffer:
    uuid: str
    name: str
    display_icon: str
    content_tier_uuid: str
    content_tier_name: str
    content_tier_color: str
    cost: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkinOffer:
        return cls(
            uuid=data["uuid"],
            name=data.get("name", "Unknown Skin"),
            display_icon=data.get("display_icon", ""),
            content_tier_uuid=data.get("content_tier_uuid", ""),
            content_tier_name=data.get("content_tier_name", "Unknown"),
            content_tier_color=data.get("content_tier_color", ""),
            cost=data.get("cost", 0),
        )


@dataclass
class BundleItem:
    uuid: str
    name: str
    display_icon: str
    base_price: int
    discounted_price: int
    discount_percent: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BundleItem:
        return cls(
            uuid=data["uuid"],
            name=data.get("name", "Unknown Item"),
            display_icon=data.get("display_icon", ""),
            base_price=data.get("base_price", 0),
            discounted_price=data.get("discounted_price", 0),
            discount_percent=data.get("discount_percent", 0.0),
        )


@dataclass
class Bundle:
    uuid: str
    name: str
    display_icon: str | None
    items: list[BundleItem]
    total_base_price: int
    total_discounted_price: int
    duration_remaining_secs: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "display_icon": self.display_icon,
            "items": [item.to_dict() for item in self.items],
            "total_base_price": self.total_base_price,
            "total_discounted_price": self.total_discounted_price,
            "duration_remaining_secs": self.duration_remaining_secs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Bundle:
        items = [BundleItem.from_dict(i) for i in data.get("items", [])]
        return cls(
            uuid=data["uuid"],
            name=data.get("name", "Unknown Bundle"),
            display_icon=data.get("display_icon"),
            items=items,
            total_base_price=data.get("total_base_price", 0),
            total_discounted_price=data.get("total_discounted_price", 0),
            duration_remaining_secs=data.get("duration_remaining_secs", 0),
        )


@dataclass
class Wallet:
    valorant_points: int
    radianite_points: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Wallet:
        return cls(
            valorant_points=data.get("valorant_points", 0),
            radianite_points=data.get("radianite_points", 0),
        )


@dataclass
class DailyStore:
    offers: list[SkinOffer]
    seconds_remaining: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "offers": [offer.to_dict() for offer in self.offers],
            "seconds_remaining": self.seconds_remaining,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailyStore:
        offers = [SkinOffer.from_dict(o) for o in data.get("offers", [])]
        return cls(
            offers=offers,
            seconds_remaining=data.get("seconds_remaining", 0),
        )


@dataclass
class StoreSnapshot:
    daily_store: DailyStore
    bundles: list[Bundle]
    wallet: Wallet
    fetched_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_store": self.daily_store.to_dict(),
            "bundles": [bundle.to_dict() for bundle in self.bundles],
            "wallet": self.wallet.to_dict(),
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoreSnapshot:
        return cls(
            daily_store=DailyStore.from_dict(data["daily_store"]),
            bundles=[Bundle.from_dict(b) for b in data.get("bundles", [])],
            wallet=Wallet.from_dict(data["wallet"]),
            fetched_at=data.get("fetched_at", time.time()),
        )
