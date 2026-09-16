# Android prototype

Native Kotlin UI with Chaquopy 17 / Python 3.10. Android 7+ (API 24),
arm64 phones and x86_64 emulators. The first version displays shop text,
wallet and bundles. Version 0.2 adds English UI, a red/black theme, weapon images
and centered short screens. Screenshots are enabled outside the Riot login page.
The reset time is updated when refreshing; a continuously ticking countdown is not yet implemented.

Version 0.3 makes SHOP CHECKER the login headline and keeps only Sign in when
signed out. The footer shows the installed version and a clickable GitHub link.
Featured bundles now show their banner and individual items. Accessories include
buddy, spray, card and title metadata with Kingdom Credit prices. Night Market
and Radianite offers appear when returned by the storefront. Missing artwork is
left out without an error placeholder. Catalog metadata refreshes daily and old
snapshots remain readable; use Refresh shop once after upgrading for new sections.

Validation for 0.3: 25 offline Python tests cover metadata aliases, bundle formats,
discount prices, KC prices, cached snapshots and existing authentication behavior.
Live accessory/bundle content still needs confirmation against the game on-device.

## Build locally

Install Android Studio (including SDK platform 35) and JDK 17, Python 3.10,
and Gradle 8.9. Open this `android` directory as the Android Studio project.
If Studio requests a wrapper, run `gradle wrapper --gradle-version 8.9`
in this directory, then sync the project. Set the Gradle JDK to 17.
Chaquopy discovers Python 3.10 using the Windows `py` launcher.

Run `gradle assembleDebug` from this directory. Output:
`app/build/outputs/apk/debug/app-debug.apk`.

Install with Android Studio Run or `adb install -r app/build/outputs/apk/debug/app-debug.apk`.
Alternatively transfer the APK to the phone and allow installation from that source.

## GitHub build

The Git repository root must be `main_project`, not its parent directory.
After committing and pushing it, open Actions > Android APK > Run workflow.
Download the `shop-checker-debug` artifact, unzip it, and install the APK.
The workflow is in `main_project/.github/workflows/android.yml`.
It uses Gradle 8.9 directly, so no wrapper binary is required for CI.
CI debug keys may differ between runs: an update can require uninstalling the old
APK, which deletes its local data. Use a stable private signing key before regular sharing.

## First phone test

1. Tap Dang nhap Riot, finish login/MFA on the Riot page.
2. The localhost redirect should close the web screen automatically.
3. The shop loads. Check that the four offers and wallet match the game.
4. Reopen the app to verify encrypted session restoration.
5. Disable the network and refresh: cached data must be clearly labeled.
6. Log out, then try another account: it must not see the first account's cache.
7. Cancel login, rotate the phone, and try an expired session.

If Riot blocks the embedded browser, stop at that result. WebView acceptance has
not been verified; do not bypass CAPTCHA or disable TLS checks. Report the visible
error and phone/Android/WebView versions, never the redirect URL or tokens.
Social sign-in / popup-based login is not implemented; test Riot username and MFA first.

## Security and boundaries

Tokens use AES-GCM with an Android Keystore key, with backups disabled.
The app does not call the desktop JSON token store. OAuth callback state and origin
are validated before any exchange. No JS/native bridge is exposed to the login page.
Network work is serialized off the UI thread; each shop request opens its own DB.
Cache databases are separated per account. Logout clears the session and web cookies;
cached shop records remain inside app storage. Android Clear storage removes everything.
Process termination during login requires starting login again.

## Validation status

Python bridge tests can run from the repository root with:
`python -m unittest discover -s tests -v`.
An Android build and real Riot WebView login still need verification in an SDK-equipped
environment and on a phone. This is a prototype, not a verified distributable APK.
