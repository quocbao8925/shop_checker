# Android work handover

## v0.3.2: post-OTP loading diagnostics

- Authentication and shop loading now have separate screens/stages. A valid
  session is saved before loading metadata or shop data.
- Authentication UI times out after 50 seconds; other worker tasks after 90
  seconds. Cancel/timeout invalidates late UI results and session writes.
- Python requests use shorter per-request timeouts; optional catalog refresh
  stops starting requests after its 12-second budget. These are not hard I/O
  deadlines: one in-flight request can still finish later. Retries cannot queue
  behind unfinished requests; REQUEST_BUSY explains this state.
- Cookie persistence runs on a separate, coalesced queue, never ahead of auth
  on the network worker. Remembered cookies are retained.
- Only sanitized AUTH/STORE/SHOP error codes reach the UI, not response bodies,
  callback URLs or credentials. No Riot API change has been confirmed.
- Needs real-device verification after OTP and with slow/offline networks.

The original prototype notes below are historical, not current build status.

Implemented a Kotlin native prototype in `android/` using Chaquopy 17 and the
existing Python engine. Initial UI uses Android Views; Compose and image cards
are deferred until the login flow is validated on hardware.

- `android_bridge.py`: state/origin checked login, account-scoped SQLite caches,
  live/cached/login-required results; bypasses desktop plaintext token persistence.
- `SessionVault.kt`: AES-GCM with Android Keystore.
- `MainActivity.kt`: embedded Riot login, redirect interception, asynchronous
  shop loading, wallet/bundle text, logout and retry.
- `auth/riot_auth.py`: geo failure now raises instead of silently selecting NA.
- `.github/workflows/android.yml`: Gradle 8.9 / JDK 17 / Python 3.10 debug APK build.
- `.gitignore`: excludes virtualenv, generated caches, local Android config and keys.

Verification: `python -m unittest discover -s tests -v` passes 15 tests.
Android SDK, Java and Gradle were not found in PATH or standard Android Studio
locations on the development machine. No APK has been built, and no real-device
login has been tested. No commits or pushes were performed.

Next: build locally with Android SDK or push this repository and run Android APK
workflow, then test Riot username/MFA and automatic redirect on a phone. If WebView
is refused by Riot, reconsider the authentication design based on that result.
See `android/README.md` for requirements, test steps and prototype limitations.
