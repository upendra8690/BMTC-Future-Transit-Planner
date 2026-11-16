# Android app (Flutter starter)

## Status: not built

- **No APK is included.** The build environment could not download the Flutter SDK, the Android SDK or the Maven and
  Google repositories. None of those hosts could be reached from the build sandbox, so no Flutter or Android build was run.
- **The starter is not compiled.** Only these static checks were run: `pubspec.yaml` and `analysis_options.yaml` were
  parsed as YAML, and `lib/main.dart` was parsed with a Dart grammar (tree-sitter) and reported zero syntax errors. Run the same checks with `python android/check_starter.py`. Install the exact versions that passed, in a separate
  virtual environment, with `python -m pip install -r requirements-android-check.txt`. Those packages are not needed to
  run the planner.
- **Nothing was run on a phone or an emulator.** Geolocation, the service worker and the back button inside the
  WebView have not been tested.

## What the starter does

`flutter_app/lib/main.dart` opens the planner web page in a full-screen WebView. The page address is set at build
time with `--dart-define=PLANNER_URL=...`. The app:

- loads only pages on the planner's own host, and sends every other link outside the app
- shows the planner's own message if the page cannot be loaded, or if no address was given at build time

It does not store data, does not request location permission itself, and does not handle the Android back button.

## Build it on a developer machine

These steps need the Flutter SDK (stable channel), the Android SDK and Java 17 or newer.

1. Accept the Android licences: `flutter doctor --android-licenses`.
2. Create the native Android folder inside the starter. This keeps the existing `lib/` and `pubspec.yaml`:

   ```
   cd android\flutter_app
   flutter create --platforms=android --project-name bmtc_planner_app .
   ```

   If `flutter create` reports that `lib/main.dart` or `pubspec.yaml` already exists, keep the starter versions.

3. Allow internet access in release builds. Open `android/app/src/main/AndroidManifest.xml` and add this line above
   `<application>`:

   ```xml
   <uses-permission android:name="android.permission.INTERNET" />
   ```

4. Check and run:

   ```
   flutter pub get
   flutter analyze
   flutter run --dart-define=PLANNER_URL=https://your-planner.example.org/
   ```

5. Build the APK only after steps 1 to 4 pass:

   ```
   flutter build apk --release --dart-define=PLANNER_URL=https://your-planner.example.org/
   ```

   The release build uses the debug signing key unless you configure your own keystore. The keystore and its
   passwords must never be placed in this project.

## Limits to know before you use it

- **The planner must be on HTTPS** for phone use. Browsers only allow location and the offline service worker on secure
  addresses. Plain-HTTP addresses such as `http://192.168.x.x:8000` are not enough for "near me" or offline use.
  See `docs/PHONE_ACCESS.md`.
- **Location inside the WebView is not wired.** Using "near me" inside this app needs Android location permission and
  WebView location handling. The starter does not do either, so the planner's location request fails and it shows a message to search by stop name
  instead.
- **No Play Store or signing setup** is included.
- **The app is a thin wrapper.** Everything shown comes from the planner web page, so the same data rules apply.

## Without building an app

Chrome on Android can install the planner as an app from the browser menu ("Install app" or "Add to Home screen"),
once the planner is served over HTTPS. The dashboard includes the manifest and service worker that this needs. In this
build the manifest and service worker were checked in headless desktop Chrome. The install step itself was not tested,
and nothing was tested on a phone.
