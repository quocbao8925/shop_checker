# Android work handover

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
