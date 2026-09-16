"""Central Application Manager for Valorant Shop Android Tool.

Orchestrates authentication, local asset caching, network requests,
and offline fallback storage.
"""

from __future__ import annotations

import logging
from pathlib import Path

from api.store_client import StoreClient, StoreApiError
from api.valorant_api import ValorantApiClient
from auth.riot_auth import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
    RiotAuthService,
)
from auth.secure_store import SecureTokenStore
from cache.db import DatabaseCache
from models import AuthTokens, StoreSnapshot

logger = logging.getLogger(__name__)


class ValorantShopManager:
    def __init__(self, storage_dir: str | Path | None = None) -> None:
        self.token_store = SecureTokenStore(storage_dir=storage_dir)
        db_path = self.token_store.storage_dir / "cache.sqlite3"
        self.cache = DatabaseCache(db_path=db_path)

        self.auth_service = RiotAuthService()
        self.api_client = ValorantApiClient()
        self.store_client = StoreClient(cache=self.cache)

        self._current_tokens: AuthTokens | None = self.token_store.load_tokens()
        self._client_version: str = self.cache.get_client_version()

    @property
    def is_authenticated(self) -> bool:
        return self._current_tokens is not None and not self._current_tokens.is_expired

    @property
    def current_tokens(self) -> AuthTokens | None:
        return self._current_tokens

    def get_login_url(self) -> str:
        """Return official Riot OAuth authorization URL."""
        return self.auth_service.get_auth_url()

    def login_with_url(self, url_or_fragment: str) -> AuthTokens:
        """Process pasted redirect URL, authenticate with Riot, and persist session.

        Also auto-syncs asset database so the shop command works immediately.
        """
        tokens = self.auth_service.authenticate_from_url(url_or_fragment)
        self.token_store.save_tokens(tokens)
        self._current_tokens = tokens

        # Auto-sync assets so shop command works right away
        try:
            self._client_version = self.api_client.sync_assets(self.cache, force=False)
        except Exception as exc:
            logger.warning("Asset sync during login failed (%s), will retry on shop fetch.", exc)

        return tokens

    def logout(self) -> None:
        """Clear session tokens and user state."""
        self.token_store.clear_tokens()
        self._current_tokens = None

    def initialize_assets(self, force: bool = False) -> str:
        """Ensure asset database and client version are up-to-date."""
        self._client_version = self.api_client.sync_assets(self.cache, force=force)
        return self._client_version

    def get_shop_data(self) -> StoreSnapshot:
        """Fetch current shop and wallet data with offline fallback.

        Raises:
            PermissionError: if not authenticated
            StoreApiError: if Riot API fails and no cache is available
        """
        if not self.is_authenticated or not self._current_tokens:
            raise PermissionError("Not authenticated. Please log in first.")

        # Ensure client version is known
        if not self._client_version:
            self._client_version = self.initialize_assets()

        try:
            snapshot = self.store_client.fetch_full_snapshot(
                self._current_tokens, self._client_version
            )
            return snapshot
        except StoreApiError as exc:
            logger.warning("Live store fetch failed: %s", exc)
            # If token might be expired, tell the user
            if self._current_tokens.is_expired:
                raise PermissionError(
                    "Your session has expired. Please run 'login' again."
                ) from exc
            # Try offline cache
            cached_snapshot = self.cache.get_store_snapshot()
            if cached_snapshot:
                logger.info("Serving offline store snapshot (may be stale).")
                return cached_snapshot
            raise
        except Exception as exc:
            logger.warning("Unexpected error fetching store: %s", exc)
            cached_snapshot = self.cache.get_store_snapshot()
            if cached_snapshot:
                logger.info("Serving offline store snapshot.")
                return cached_snapshot
            raise

    def get_cached_shop_data(self) -> StoreSnapshot | None:
        """Retrieve cached store data without initiating network requests."""
        return self.cache.get_store_snapshot()

    def close(self) -> None:
        """Close cache connections and release resources."""
        self.cache.close()
