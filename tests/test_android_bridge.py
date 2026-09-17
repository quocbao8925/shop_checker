import json
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.parse import parse_qs, urlparse

import android_bridge as bridge
from auth.riot_auth import AuthenticationError, RiotAuthService
from models import AuthTokens, StoreSnapshot, DailyStore, Wallet
from api.store_client import StoreApiError


class AndroidBridgeTests(unittest.TestCase):
    def test_login_url_allows_remembered_session_and_encodes_state(self):
        state = "random-state&prompt=login"
        url = urlparse(bridge.login_url(state))
        query = parse_qs(url.query)
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.hostname, "auth.riotgames.com")
        self.assertNotIn("prompt", query)
        self.assertEqual(query["state"], [state])
        self.assertEqual(query["nonce"], [state])
        self.assertEqual(query["redirect_uri"], ["http://localhost/redirect"])

    def tokens(self, account="account-a"):
        return AuthTokens("access", "id", "entitlements", account, "ap", "ap")

    def test_rejects_wrong_origin_state_and_missing_id_before_network(self):
        with patch.object(bridge.RiotAuthService, "authenticate_from_url") as auth:
            for url in [
                "https://evil.test/redirect#access_token=a&id_token=b&state=s",
                "http://localhost.evil.test/redirect#access_token=a&id_token=b&state=s",
                "http://localhost/redirect#access_token=a&id_token=b&state=wrong",
                "http://localhost/redirect#access_token=a&state=s",
            ]:
                with self.assertRaises(AuthenticationError):
                    bridge.authenticate(url, "s")
            auth.assert_not_called()

    def test_callback_preserves_full_url(self):
        url = "http://localhost/redirect#access_token=a&id_token=b&state=s&expires_in=3600"
        with patch.object(bridge.RiotAuthService, "authenticate_from_url", return_value=self.tokens()) as auth:
            self.assertEqual(json.loads(bridge.authenticate(url, "s"))["shard"], "ap")
            auth.assert_called_once_with(url)

    def test_expired_session_never_calls_network(self):
        tokens = self.tokens()
        tokens.expires_in = 0
        with patch.object(bridge, "StoreClient") as client:
            self.assertEqual(json.loads(bridge.shop("unused", json.dumps(tokens.to_dict())))["status"], "login_required")
            client.assert_not_called()

    def test_cache_is_account_scoped_and_marked_stale(self):
        snapshot = StoreSnapshot(DailyStore([], 100), [], Wallet(25, 10))
        def save_snapshot(client, tokens, version):
            client.cache.save_store_snapshot(snapshot)
            return snapshot
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(bridge.ValorantApiClient, "sync_assets", return_value="version"), \
                patch.object(bridge.ValorantApiClient, "sync_accessories"), \
                patch.object(bridge.StoreClient, "fetch_full_snapshot", autospec=True, side_effect=save_snapshot):
            session = json.dumps(self.tokens().to_dict())
            self.assertEqual(json.loads(bridge.shop(directory, session))["status"], "live")
            with patch.object(bridge.StoreClient, "fetch_full_snapshot", side_effect=StoreApiError("offline")):
                self.assertEqual(json.loads(bridge.shop(directory, session))["status"], "cached")
                other = json.dumps(self.tokens("account-b").to_dict())
                self.assertEqual(json.loads(bridge.shop(directory, other))["status"], "unavailable")
            with patch.object(bridge.StoreClient, "fetch_full_snapshot", side_effect=StoreApiError("HTTP 401")):
                self.assertEqual(json.loads(bridge.shop(directory, session))["status"], "login_required")

    def test_geo_failure_does_not_assume_na(self):
        session = Mock()
        session.put.return_value.ok = False
        session.put.return_value.status_code = 401
        with self.assertRaises(AuthenticationError):
            RiotAuthService().fetch_region_and_shard("access", "id", session)
