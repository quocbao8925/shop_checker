"""Client for public valorant-api.com endpoints.

Fetches weapon skins, content tiers, bundles, and Riot client version
to resolve opaque UUIDs into rich UI assets.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from cache.db import DatabaseCache

logger = logging.getLogger(__name__)

BASE_URL = "https://valorant-api.com/v1"


class ValorantApiClient:
    def __init__(self, base_url: str = BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_version(self) -> str:
        """Fetch latest Riot client version from valorant-api.com."""
        url = f"{self.base_url}/version"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        version: str = data.get("data", {}).get("riotClientVersion", "")
        return version

    def fetch_skins(self) -> list[dict[str, Any]]:
        """Fetch all weapon skins."""
        url = f"{self.base_url}/weapons/skins"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def fetch_content_tiers(self) -> list[dict[str, Any]]:
        """Fetch all content tiers."""
        url = f"{self.base_url}/contenttiers"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def fetch_bundles(self) -> list[dict[str, Any]]:
        """Fetch all featured bundles."""
        url = f"{self.base_url}/bundles"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def load_seed_assets(self, cache: DatabaseCache) -> str:
        """Load bundled seed assets into local cache when network is unavailable."""
        import json
        from pathlib import Path

        seed_file = Path(__file__).resolve().parent.parent / "assets" / "seed_assets.json"
        if not seed_file.exists():
            raise FileNotFoundError(f"Seed assets file not found: {seed_file}")

        logger.info("Loading bundled seed assets from %s...", seed_file)
        with open(seed_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        version = data.get("client_version", "release-09.05")
        cache.save_assets(
            skins_data=data.get("skins", []),
            tiers_data=data.get("content_tiers", []),
            bundles_data=data.get("bundles", []),
            client_version=version,
        )
        return version

    def sync_assets(self, cache: DatabaseCache, force: bool = False) -> str:
        """Fetch and populate local SQLite cache with latest assets and version.

        Returns the dynamic client version string.
        Falls back to local cache or bundled seed assets if network fails.
        """
        fresh = time.time() - float(cache.get_metadata("last_synced", "0")) < 86400
        if not force and fresh and cache.has_assets():
            cached_version = cache.get_client_version()
            if cached_version:
                logger.info("Using cached assets and client version: %s", cached_version)
                return cached_version

        logger.info("Syncing assets from %s...", self.base_url)
        try:
            version = self.fetch_version()
            skins = self.fetch_skins()
            tiers = self.fetch_content_tiers()
            bundles = self.fetch_bundles()

            cache.save_assets(
                skins_data=skins,
                tiers_data=tiers,
                bundles_data=bundles,
                client_version=version,
            )
            return version
        except Exception as exc:
            logger.warning("Failed to sync fresh live assets (%s).", exc)
            if cache.has_assets():
                cached_version = cache.get_client_version()
                logger.info("Falling back to existing cached assets (version: %s)", cached_version)
                return cached_version

            logger.info("Falling back to bundled seed assets...")
            return self.load_seed_assets(cache)



    def sync_accessories(self, cache: DatabaseCache, max_seconds: float | None = None) -> None:
        """Refresh independent catalogs daily, retaining cached data on failure."""
        started = time.monotonic()
        for endpoint, kind in (
            ("buddies", "Gun buddy"), ("sprays", "Spray"),
            ("playercards", "Player card"), ("playertitles", "Player title"),
            ("currencies", "Currency"),
        ):
            stamp = "catalog_synced_" + endpoint
            if time.time() - float(cache.get_metadata(stamp, "0")) < 86400:
                continue
            remaining = (max_seconds - (time.monotonic() - started)) if max_seconds is not None else 8
            if remaining <= 0:
                break
            try:
                response = self.session.get(
                    f"{self.base_url}/{endpoint}", params={"language": "en-US"},
                    timeout=min(self.timeout, 8, max(0.1, remaining)),
                )
                response.raise_for_status()
                rows = []
                for item in response.json().get("data", []):
                    name = item.get("displayName") or item.get("titleText") or kind
                    icon = (item.get("largeArt") or item.get("fullTransparentIcon")
                            or item.get("displayIcon") or "")
                    entry = dict(uuid=item["uuid"], display_name=name,
                                 display_icon=icon, kind=kind)
                    rows.append(entry)
                    for level in item.get("levels", []) or []:
                        rows.append({**entry, "uuid": level["uuid"]})
                cache.save_catalog_items(rows)
                cache.set_metadata(stamp, str(time.time()))
            except Exception:
                # Optional metadata must never prevent viewing the store.
                logger.warning("Could not refresh %s catalog; keeping cached metadata.", endpoint)
