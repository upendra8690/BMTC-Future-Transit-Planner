# Android emulator test (20 November 2026): not completed

**Result: no APK was built on this computer, so no app test ran on the emulator.** Nothing in this file is a device
or emulator test result. Physical-device testing has never been done.

## What was done
| Step | Result |
|---|---|
| Android SDK, emulator 36.2.12 and the API 36 Google APIs x86_64 image | Present on the owner's Windows computer |
| Hardware acceleration | `emulator -accel-check`: WHPX installed and usable |
| Virtual device | `btp_test` created (1080 × 2400, 420 dpi, 3 GB RAM, Android 16 / API 36). It booted: `sys.boot_completed=1` |
| Build tools | Flutter 3.50.0 stable and Temurin JDK 21.0.13 unpacked in `%LOCALAPPDATA%\btp-tools` |
| Test APK build (`scripts/android/build_test_apk.ps1`, the CI steps, `PLANNER_URL=https://bengaluru-transit-planner-v4.onrender.com/`) | **Failed** at `flutter create` / `flutter pub get` |

## Why it failed
Flutter's package tool could not open connections to pub.dev:
`SocketException: Connection failed (OS Error: An attempt was made to access a socket in a way forbidden by its access
permissions, errno = 10013)`.

The network itself works:
- the same `dart.exe` running a small script fetched pub.dev, including twelve requests in parallel (all HTTP 200);
- PowerShell also reached pub.dev.

The refusal is specific to the package tool's connections on this computer. A local security setting, such as a
firewall or antivirus rule, is the likely cause; it was not changed. Three attempts gave the same error.

The CI build was not used either. On `v4` pushes it builds against a placeholder address and keeps no APK. Keeping one
needs the variable `V4_PLANNER_URL` and a manual run that publishes the `app-v4-preview` pre-release. That is the
owner's decision, and `tests/test_release_guard.py` deliberately enforces it.

## How to finish the test
1. **Get an APK**, either:
   - on this computer: allow `dart.exe` (in `%LOCALAPPDATA%\btp-tools\flutter\flutter\bin\cache\dart-sdk\bin`)
     through the firewall or antivirus, then run `scripts\android\build_test_apk.ps1`; or
   - in GitHub: set the repository variable `V4_PLANNER_URL` to `https://bengaluru-transit-planner-v4.onrender.com/`,
     then run the "Android APK" workflow on `v4` with `publish_v4_preview` ticked. This publishes a pre-release; it
     needs the owner's approval.
2. **Boot the emulator:** `emulator -avd btp_test`.
3. **Run the test:** `python tests/android/emulator_check.py <path to app-release.apk> <output folder>`.

   It covers installation, navigation, the map, journey planning, the location prompt, the back button, external
   links, three screen sizes, a restart, offline use, an offline cold start with retry, and the account screen. Each
   step saves a screenshot and writes `results.txt`.

Sign-in cannot be tested in the app against the public service, because accounts there are off until a permanent
database exists. Sign-in is verified in a browser instead (`tests/browser/accounts_check.py` 24/24).
