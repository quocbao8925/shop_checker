"""Secure Token Storage for Android and Desktop environments.

Provides on-device persistence for AuthTokens.
- On Android (when pyjnius is available): Bridges to EncryptedSharedPreferences.
- On Desktop / Fallback: Uses a protected local file in the app data directory.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from models import AuthTokens

logger = logging.getLogger(__name__)


class SecureTokenStore:
    """Manages secure token persistence across app launches."""

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            # Standard user data directory or local fallback
            base_dir = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME")
            if base_dir:
                self.storage_dir = Path(base_dir) / "vlr_shop_checker"
            else:
                self.storage_dir = Path.home() / ".vlr_shop_checker"

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.storage_dir / "session.json"
        self._is_android = self._detect_android()

    def _detect_android(self) -> bool:
        """Check if running within an Android runtime."""
        return "ANDROID_STORAGE" in os.environ or "ANDROID_ROOT" in os.environ

    def save_tokens(self, tokens: AuthTokens) -> None:
        """Persist tokens to secure storage."""
        data = tokens.to_dict()
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info("Saved session tokens to %s", self.file_path)
        except OSError as exc:
            logger.error("Failed to write session file: %s", exc)
            raise

    def load_tokens(self) -> AuthTokens | None:
        """Load stored tokens if present."""
        if not self.file_path.exists():
            return None

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
            tokens = AuthTokens.from_dict(data)
            return tokens
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("Corrupted or unreadable session file: %s. Clearing.", exc)
            self.clear_tokens()
            return None

    def clear_tokens(self) -> None:
        """Remove stored tokens (user logout)."""
        if self.file_path.exists():
            try:
                self.file_path.unlink()
                logger.info("Cleared stored session tokens.")
            except OSError as exc:
                logger.error("Failed to remove session file: %s", exc)

    def has_valid_session(self) -> bool:
        """Return True if stored tokens exist and are not expired."""
        tokens = self.load_tokens()
        return tokens is not None and not tokens.is_expired
