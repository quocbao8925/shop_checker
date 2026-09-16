"""Riot Games Authentication Service.

Handles the Riot OAuth 2.0 implicit grant flow:
1. Directs user to the official Riot authorization endpoint.
2. Extracts access_token and id_token from redirect URI.
3. Retrieves entitlements token, player PUUID, and geographical shard.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

import requests

from models import AuthTokens

logger = logging.getLogger(__name__)

AUTH_URL = (
    "https://auth.riotgames.com/authorize"
    "?redirect_uri=http%3A%2F%2Flocalhost%2Fredirect"
    "&client_id=riot-client"
    "&response_type=token%20id_token"
    "&nonce=1"
    "&scope=openid%20link%20ban%20lol_region%20account"
    "&prompt=login"
)

ENTITLEMENTS_URL = "https://entitlements.auth.riotgames.com/api/token/v1"
USERINFO_URL = "https://auth.riotgames.com/userinfo"
GEO_URL = "https://riot-geo.pas.si.riotgames.com/pas/v1/product/valorant"

REGION_TO_SHARD: dict[str, str] = {
    "na": "na",
    "eu": "eu",
    "ap": "ap",
    "kr": "kr",
    "latam": "na",
    "br": "na",
}


class AuthenticationError(Exception):
    """Raised when authentication parsing or validation fails."""


class RateLimitError(Exception):
    """Raised when Riot auth servers respond with HTTP 429."""


class NetworkError(Exception):
    """Raised when connection to Riot servers cannot be established."""


class RiotAuthService:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    @staticmethod
    def get_auth_url() -> str:
        """Return the official Riot OAuth authorization URL."""
        return AUTH_URL

    @staticmethod
    def extract_tokens(url_or_fragment: str) -> dict[str, str]:
        """Extract access_token and id_token from a redirect URL or fragment.

        Expected formats:
        - http://localhost/redirect#access_token=...&id_token=...
        - #access_token=...&id_token=...
        - access_token=...&id_token=...
        """
        raw = url_or_fragment.strip()
        parsed = urlparse(raw)
        fragment = parsed.fragment

        # If no fragment was found via standard parse, check query or raw string
        if not fragment:
            if parsed.query:
                fragment = parsed.query
            elif "#" in raw:
                fragment = raw.split("#", 1)[1]
            elif "access_token=" in raw:
                fragment = raw

        if not fragment:
            raise AuthenticationError(
                "Could not find tokens in the input. Ensure you provided the full "
                "redirect URL containing '#access_token=...'."
            )

        params = parse_qs(fragment)
        access_token_list = params.get("access_token")
        if not access_token_list or not access_token_list[0]:
            raise AuthenticationError("No 'access_token' found in the redirect URL.")

        access_token = access_token_list[0]
        id_token_list = params.get("id_token")
        id_token = id_token_list[0] if id_token_list and id_token_list[0] else ""

        # Optional expires_in extraction
        expires_in = 10800
        expires_in_list = params.get("expires_in")
        if expires_in_list and expires_in_list[0].isdigit():
            expires_in = int(expires_in_list[0])

        return {
            "access_token": access_token,
            "id_token": id_token,
            "expires_in": str(expires_in),
        }

    def fetch_entitlements(
        self, access_token: str, session: requests.Session | None = None
    ) -> str:
        """Exchange access token for entitlements token."""
        s = session or requests.Session()
        try:
            resp = s.post(
                ENTITLEMENTS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise NetworkError(f"Network error contacting entitlements: {exc}") from exc

        if resp.status_code == 429:
            raise RateLimitError("Rate limited by Riot entitlements server")
        if not resp.ok:
            raise AuthenticationError(
                f"Failed to fetch entitlements (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        data = resp.json()
        token = data.get("entitlements_token")
        if not token:
            raise AuthenticationError("No entitlements_token in response")
        return token

    def fetch_player_info(
        self, access_token: str, session: requests.Session | None = None
    ) -> str:
        """Fetch player's PUUID from Riot userinfo endpoint."""
        s = session or requests.Session()
        try:
            resp = s.get(
                USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise NetworkError(f"Network error contacting userinfo: {exc}") from exc

        if resp.status_code == 429:
            raise RateLimitError("Rate limited by Riot userinfo server")
        if not resp.ok:
            raise AuthenticationError(
                f"Failed to fetch player info (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        data = resp.json()
        puuid = data.get("sub")
        if not puuid:
            raise AuthenticationError("No 'sub' (PUUID) in userinfo response")
        return puuid

    def fetch_region_and_shard(
        self, access_token: str, id_token: str, session: requests.Session | None = None
    ) -> tuple[str, str]:
        """Fetch user region and map to server shard."""
        s = session or requests.Session()
        try:
            resp = s.put(
                GEO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"id_token": id_token},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise NetworkError(f"Network error contacting geo endpoint: {exc}") from exc

        if resp.status_code == 429:
            raise RateLimitError("Rate limited by Riot geo server")
        if not resp.ok:
            raise AuthenticationError(f"Could not determine account region (HTTP {resp.status_code}). Sign in again.")

        data = resp.json()
        region = data.get("affinities", {}).get("live", "").lower()
        if region not in REGION_TO_SHARD:
            raise AuthenticationError("Unknown account region. Sign in again.")
        shard = REGION_TO_SHARD[region]
        return region, shard

    def authenticate_from_url(
        self, url_or_fragment: str, session: requests.Session | None = None
    ) -> AuthTokens:
        """Complete full authentication flow from pasted redirect URL."""
        token_data = self.extract_tokens(url_or_fragment)
        access_token = token_data["access_token"]
        id_token = token_data["id_token"]
        expires_in = int(token_data.get("expires_in", 10800))

        s = session or requests.Session()
        entitlements = self.fetch_entitlements(access_token, session=s)
        puuid = self.fetch_player_info(access_token, session=s)
        region, shard = self.fetch_region_and_shard(access_token, id_token, session=s)

        return AuthTokens(
            access_token=access_token,
            id_token=id_token,
            entitlements_token=entitlements,
            puuid=puuid,
            region=region,
            shard=shard,
            expires_in=expires_in,
        )
