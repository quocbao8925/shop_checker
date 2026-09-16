"""SQLite local cache for Valorant assets, metadata, and shop state.

Provides offline support and high-performance O(1) lookups for skins,
bundles, content tiers, and client version strings.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from models import ContentTier, StoreSnapshot

logger = logging.getLogger(__name__)


class DatabaseCache:
    """Thread-safe SQLite local cache."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn:
            self._conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Metadata key-value store
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Skins master table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skins (
                    uuid TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    display_icon TEXT,
                    content_tier_uuid TEXT
                )
            """)

            # Skin levels mapping (maps level_uuid -> parent skin_uuid)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skin_levels (
                    level_uuid TEXT PRIMARY KEY,
                    skin_uuid TEXT NOT NULL,
                    FOREIGN KEY (skin_uuid) REFERENCES skins (uuid)
                )
            """)

            # Content tiers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content_tiers (
                    uuid TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    highlight_color TEXT,
                    display_icon TEXT
                )
            """)

            # Bundles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bundles (
                    uuid TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    display_icon TEXT,
                    description TEXT
                )
            """)

            # Offline Store Snapshot table (single row with id=1)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS store_snapshot (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    data_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            conn.commit()

    def save_assets(
        self,
        skins_data: list[dict[str, Any]],
        tiers_data: list[dict[str, Any]],
        bundles_data: list[dict[str, Any]],
        client_version: str,
    ) -> None:
        """Batch save all asset data fetched from valorant-api.com."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Update client version & sync timestamp
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("client_version", client_version),
            )
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("last_synced", str(time.time())),
            )

            # Insert or replace Content Tiers
            tier_rows = [
                (
                    t["uuid"].lower(),
                    t.get("devName", "") or t.get("displayName", "Unknown"),
                    t.get("highlightColor", "") or "",
                    t.get("displayIcon", "") or "",
                )
                for t in tiers_data
            ]
            cursor.executemany(
                "INSERT OR REPLACE INTO content_tiers (uuid, name, highlight_color, display_icon) "
                "VALUES (?, ?, ?, ?)",
                tier_rows,
            )

            # Insert or replace Skins & Level mappings
            skin_rows = []
            level_rows = []

            for s in skins_data:
                skin_uuid = s["uuid"].lower()
                display_name = s.get("displayName", "Unknown Skin")

                # Fallback to chromas fullRender if displayIcon is empty
                display_icon = s.get("displayIcon") or ""
                if not display_icon and s.get("chromas"):
                    display_icon = s["chromas"][0].get("fullRender") or ""

                tier_uuid = (s.get("contentTierUuid") or "").lower()
                skin_rows.append((skin_uuid, display_name, display_icon, tier_uuid))

                for lvl in s.get("levels", []):
                    lvl_uuid = lvl["uuid"].lower()
                    level_rows.append((lvl_uuid, skin_uuid))

            cursor.executemany(
                "INSERT OR REPLACE INTO skins (uuid, display_name, display_icon, content_tier_uuid) "
                "VALUES (?, ?, ?, ?)",
                skin_rows,
            )
            cursor.executemany(
                "INSERT OR REPLACE INTO skin_levels (level_uuid, skin_uuid) VALUES (?, ?)",
                level_rows,
            )

            # Insert or replace Bundles
            bundle_rows = [
                (
                    b["uuid"].lower(),
                    b.get("displayName", "Unknown Bundle"),
                    b.get("displayIcon") or b.get("displayIcon2") or "",
                    b.get("description", "") or "",
                )
                for b in bundles_data
            ]
            cursor.executemany(
                "INSERT OR REPLACE INTO bundles (uuid, display_name, display_icon, description) "
                "VALUES (?, ?, ?, ?)",
                bundle_rows,
            )

            conn.commit()
            logger.info(
                "Assets saved: %d skins, %d levels, %d tiers, %d bundles, version=%s",
                len(skin_rows),
                len(level_rows),
                len(tier_rows),
                len(bundle_rows),
                client_version,
            )

    def get_skin(self, uuid: str) -> dict[str, Any] | None:
        """Resolve a skin by either its skin UUID or a skin level UUID."""
        key = uuid.lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Try skin uuid directly
            cursor.execute(
                "SELECT uuid, display_name, display_icon, content_tier_uuid FROM skins WHERE uuid = ?",
                (key,),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

            # Try through skin_levels mapping
            cursor.execute(
                """
                SELECT s.uuid, s.display_name, s.display_icon, s.content_tier_uuid
                FROM skin_levels sl
                JOIN skins s ON sl.skin_uuid = s.uuid
                WHERE sl.level_uuid = ?
                """,
                (key,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_content_tier(self, uuid: str) -> ContentTier | None:
        """Retrieve content tier details by UUID."""
        if not uuid:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT uuid, name, highlight_color, display_icon FROM content_tiers WHERE uuid = ?",
                (uuid.lower(),),
            )
            row = cursor.fetchone()
            if row:
                return ContentTier(
                    uuid=row["uuid"],
                    name=row["name"],
                    highlight_color=row["highlight_color"],
                    display_icon=row["display_icon"],
                )
            return None

    def get_bundle(self, uuid: str) -> dict[str, Any] | None:
        """Retrieve bundle details by UUID."""
        if not uuid:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT uuid, display_name, display_icon, description FROM bundles WHERE uuid = ?",
                (uuid.lower(),),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_client_version(self) -> str:
        """Get the cached Riot client version."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = 'client_version'")
            row = cursor.fetchone()
            return row["value"] if row else ""

    def has_assets(self) -> bool:
        """Check if asset data is populated in the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM skins")
            row = cursor.fetchone()
            return bool(row and row["count"] > 0)

    def save_store_snapshot(self, snapshot: StoreSnapshot) -> None:
        """Save latest store rotation and wallet balance for offline access."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            data_json = json.dumps(snapshot.to_dict())
            cursor.execute(
                "INSERT OR REPLACE INTO store_snapshot (id, data_json, updated_at) VALUES (1, ?, ?)",
                (data_json, time.time()),
            )
            conn.commit()

    def get_store_snapshot(self) -> StoreSnapshot | None:
        """Retrieve offline store snapshot if available."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM store_snapshot WHERE id = 1")
            row = cursor.fetchone()
            if row:
                try:
                    data = json.loads(row["data_json"])
                    return StoreSnapshot.from_dict(data)
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning("Could not parse store snapshot: %s", exc)
            return None
