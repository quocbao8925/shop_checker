# Valorant Shop Android Tool (`main_project`)

## Native Android prototype

See [Android build and phone testing instructions](android/README.md).
The Kotlin/Chaquopy prototype includes automatic login redirect capture,
Keystore-encrypted sessions, and a basic native shop screen. GitHub Actions
configuration is at `.github/workflows/android.yml`. Android compilation and
real-device login are pending; Python core and bridge tests pass (15 tests).

A safe, standalone, on-device Valorant Daily Storefront viewer for Android and Desktop.

## Architecture

This project is built based on the principles outlined in `valorant-shop-android-tool.md` and the proven endpoints in `reference_repo`:
- **Direct On-Device Network**: Direct communication with Riot Games authentication and storefront endpoints — no intermediate servers storing user credentials.
- **Riot OAuth 2.0 Implicit Grant**: Authenticates directly against official Riot servers (`auth.riotgames.com`).
- **Dynamic Asset & Version Resolution**: Resolves opaque game UUIDs and dynamic `riotClientVersion` via `valorant-api.com` with bundled seed fallback.
- **Local Persistence & Caching**: SQLite-backed local cache for skins, content tiers, bundles, and offline storefront snapshots.
- **Token Security**: Tokens are isolated and managed via `SecureTokenStore` (prepared for Android Keystore / `EncryptedSharedPreferences`).

---

## Directory Structure

```text
main_project/
├── main.py                     # App CLI entry point & coordinator
├── manager.py                  # High-level orchestrator (ValorantShopManager)
├── models.py                   # Dataclasses: AuthTokens, SkinOffer, Bundle, Wallet
├── requirements.txt            # Python dependencies
├── buildozer.spec              # Android APK buildozer configuration
├── api/
│   ├── __init__.py
│   ├── valorant_api.py         # valorant-api.com client & asset synchronizer
│   └── store_client.py         # Riot PD storefront & wallet endpoint client
├── auth/
│   ├── __init__.py
│   ├── riot_auth.py            # Riot OAuth flow, token parsing & entitlements
│   └── secure_store.py         # On-device session token persistence
├── cache/
│   ├── __init__.py
│   └── db.py                   # SQLite cache for assets, tiers, bundles & offline store
├── assets/
│   └── seed_assets.json        # Pre-bundled offline fallback assets
└── tests/
    ├── __init__.py
    └── test_core.py            # Comprehensive unit tests
```

---

## Quickstart & CLI Usage

### 1. Check Status
```bash
python main.py status
```

### 2. Synchronize Assets
Synchronizes weapon skins, content tiers, and client version into SQLite:
```bash
python main.py sync
```

### 3. Log In via Riot OAuth
```bash
python main.py login
```
Follow the URL provided to sign in on Riot's official login page. Copy the redirect URL (`http://localhost/redirect#access_token=...`) and authenticate:
```bash
python main.py auth "<PASTED_URL>"
```

### 4. View Daily Shop, Bundles, and Wallet
```bash
python main.py shop
```

### 5. Log Out
```bash
python main.py logout
```

---

## Running Unit Tests
```bash
python -m unittest tests.test_core -v
```

---

## Android Packaging with Buildozer
```bash
cd main_project
buildozer -v android debug
```
