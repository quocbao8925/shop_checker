"""Android bridge: only the native Keystore vault persists tokens."""
import hashlib
import json
import re
import requests
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from auth.riot_auth import RiotAuthService, AuthenticationError, NetworkError, RateLimitError, AUTH_URL
from api.store_client import StoreClient, StoreApiError
from api.valorant_api import ValorantApiClient
from cache.db import DatabaseCache
from models import AuthTokens

def login_url(state):
    # Let Riot reuse remembered WebView cookies. Never force a fresh password/MFA.
    parsed = urlparse(AUTH_URL)
    params = parse_qs(parsed.query)
    params.pop("prompt", None)
    params["nonce"] = [state]
    params["state"] = [state]
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

def authenticate(url, state):
    parsed = urlparse(url)
    params = parse_qs(parsed.fragment)
    if (parsed.scheme != "http" or parsed.netloc != "localhost"
            or parsed.path != "/redirect" or params.get("state") != [state]
            or not params.get("id_token")):
        raise AuthenticationError("Invalid login callback")
    return json.dumps(RiotAuthService(timeout=12).authenticate_from_url(url).to_dict())

def safe_error(exc, stage):
    """Only allowlisted codes leave Python, never a URL, token or response body."""
    status = re.search(r"HTTP (\d{3})", str(exc))
    if isinstance(exc, RateLimitError):
        return stage + "_HTTP_429"
    if status:
        return stage + "_HTTP_" + status.group(1)
    if isinstance(exc, (requests.Timeout, NetworkError, requests.ConnectionError)):
        return stage + "_NETWORK"
    return stage + "_FAILED"

def authenticate_result(url, state):
    try:
        return json.dumps({"status": "authenticated", "session": json.loads(authenticate(url, state))})
    except Exception as exc:
        return json.dumps({"status": "error", "code": safe_error(exc, "AUTH")})

def shop(storage_dir, session_json):
    tokens = AuthTokens.from_dict(json.loads(session_json))
    if tokens.is_expired:
        return json.dumps({"status": "login_required"})
    account = hashlib.sha256(tokens.puuid.encode()).hexdigest()
    cache = DatabaseCache(Path(storage_dir) / (account + ".sqlite3"))
    client = StoreClient(cache, timeout=12)
    assets = ValorantApiClient(timeout=8)
    try:
        version = assets.sync_assets(cache)
        assets.sync_accessories(cache, max_seconds=12)
        if cache.has_assets():
            try:
                version = assets.fetch_version() or version
            except Exception:
                pass  # Cached version remains usable when metadata service is offline.
        try:
            snapshot = client.fetch_full_snapshot(tokens, version)
            return json.dumps({"status": "live", "snapshot": snapshot.to_dict()})
        except StoreApiError as exc:
            if "HTTP 401" in str(exc):
                return json.dumps({"status": "login_required"})
            cached = cache.get_store_snapshot()
            if cached:
                return json.dumps({"status": "cached", "snapshot": cached.to_dict(), "code": safe_error(exc, "STORE")})
            return json.dumps({"status": "unavailable", "code": safe_error(exc, "STORE")})
    except Exception as exc:
        return json.dumps({"status": "unavailable", "code": safe_error(exc, "SHOP")})
    finally:
        assets.session.close()
        client.session.close()
        cache.close()
