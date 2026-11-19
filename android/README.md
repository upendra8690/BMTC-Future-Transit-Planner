# Android app (Flutter WebView wrapper)

## Status (18 November 2026)
- **Built by GitHub Actions** (`.github/workflows/android-apk.yml`). Every push to `v4` that changes `android/` runs
  `flutter analyze` and builds a release APK and a Play bundle (AAB), as a compile check only. **Nothing is kept or
  published from `v4`.** A pre-release needs a manual run with `publish_v4_preview` and the `V4_PLANNER_URL` variable,
  and the owner's approval (`tests/test_release_guard.py`).
- **Not yet run on a phone or an emulator.** The development computer has no Flutter SDK; see "Testing" below.
- **Signing:** without the owner's release key, builds are signed with Flutter's debug key and are **not** for Google
  Play. See "Release key".

## What the wrapper does (`flutter_app/lib/main.dart`)
| Behaviour | How |
|---|---|
| Shows the planner | A full-screen WebView of the address given at build time (`--dart-define=PLANNER_URL=...`) |
| Links | Planner pages open inside the app; `tel:` links (SOS, helplines) open the dialler; other `https` links open the browser; nothing else is followed |
| Back button | Goes back a page inside the app; closes the app when there is none |
| "Stops near me" | When the page asks for the location, Android asks the passenger, then and only then. Only the planner's own address can ask, and the WebView never keeps the permission |
| Downloads (timetable CSV, PDFs) | The page sends the file through one named channel (`PlannerAndroid`); the app accepts only CSV, PDF or JSON up to about 7.5 MB, writes it to its temporary folder and opens Android's share sheet |
| Load errors | A clear message and **Try again** |
| Backup | Switched off (`android:allowBackup="false"`), so the device key and saved journeys stay on the phone |
| Play requirements | Target and compile API level at least 36 (checked on every build); version code = workflow run number |
| Permissions | Internet; location (asked only when needed) |

Static check without Flutter: `python android/check_starter.py` (needs `requirements-android-check.txt`).

## Release key (owner only)
1. Create an upload key on your own computer, for example with Android Studio's JDK:
   `keytool -genkeypair -v -keystore upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload`.
   Keep the file and its passwords in a safe place **outside** this repository.
2. Encode it: `base64 -w 0 upload-keystore.jks` (Linux) or `[Convert]::ToBase64String([IO.File]::ReadAllBytes("upload-keystore.jks"))`
   (PowerShell).
3. In GitHub: **Settings > Secrets and variables > Actions > New repository secret**. Add `ANDROID_KEYSTORE_BASE64`,
   `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD`.
4. **Never paste the key or its passwords into a chat, an issue or a commit.**

The next build then signs the APK and AAB with that key. This path has not been run yet, because no key exists.

## Testing
- **Emulator.** The development computer has the Android SDK, the emulator and Android 16 (API 36) images. An APK
  pointing at the public address is needed: either the owner approves setting `V4_PLANNER_URL`, or Flutter is
  installed locally to build one.
- **Phone.** Install the APK, then check: the planner opens; "Stops near me" asks for location and works; SOS opens the
  dialler with 112; an official link opens the browser; the back button; a timetable CSV download opens the share
  sheet; airplane mode shows the offline copy or "Try again".

## Build on a developer machine
Requires the Flutter SDK (stable), the Android SDK and Java 17 or newer.
```
cd android/flutter_app
flutter create --platforms=android --project-name bmtc_planner_app --org io.github.upendra8690 .
```
Then apply the manifest and Gradle changes that the workflow makes (permissions, backup off, API level 36), and:
```
flutter pub get
flutter analyze
flutter run --dart-define=PLANNER_URL=https://bengaluru-transit-planner-v4.onrender.com/
```

## Limits
- The wrapper adds no data of its own; every data rule of the web app applies.
- Google Play may judge a thin website wrapper as offering too little beyond the website. That is a risk to weigh
  before submitting it.
