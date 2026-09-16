"""Android bridge: only the native Keystore vault persists tokens."""
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from auth.riot_auth import RiotAuthService, AuthenticationError, AUTH_URL
from api.store_client import StoreClient, StoreApiError
from api.valorant_api import ValorantApiClient
from cache.db import DatabaseCache
from models import AuthTokens

def login_url(state):
    return AUTH_URL.replace("nonce=1", "nonce=" + state) + "&" + urlencode({"state": state})

def authenticate(url, state):
    parsed = urlparse(url)
    params = parse_qs(parsed.fragment)
    if (parsed.scheme != "http" or parsed.netloc != "localhost"
            or parsed.path != "/redirect" or params.get("state") != [state]
            or not params.get("id_token")):
        raise AuthenticationError("Invalid login callback")
    return json.dumps(RiotAuthService().authenticate_from_url(url).to_dict())

def shop(storage_dir, session_json):
    tokens = AuthTokens.from_dict(json.loads(session_json))
    if tokens.is_expired:
        return json.dumps({"status": "login_required"})
    account = hashlib.sha256(tokens.puuid.encode()).hexdigest()
    cache = DatabaseCache(Path(storage_dir) / (account + ".sqlite3"))
    client = StoreClient(cache)
    assets = ValorantApiClient()
    try:
        version = assets.sync_assets(cache)
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
                return json.dumps({"status": "cached", "snapshot": cached.to_dict()})
            return json.dumps({"status": "unavailable"})
    finally:
        assets.session.close()
        client.session.close()
        cache.close()
