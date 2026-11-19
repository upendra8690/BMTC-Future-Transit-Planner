# Builds a test APK on Windows the way .github/workflows/android-apk.yml does, pointing at the live v4 service.
# Needs Flutter stable in %LOCALAPPDATA%\btp-tools\flutter\flutter, JDK 21 in %LOCALAPPDATA%\btp-tools\jdk,
# the Android SDK in %LOCALAPPDATA%\Android\Sdk, and network access for dart.exe (pub.dev) and Gradle (Maven).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\android\build_test_apk.ps1
$ErrorActionPreference = "Continue"
function Step($what) { if ($LASTEXITCODE -ne 0) { "STEP FAILED: $what (exit $LASTEXITCODE)"; exit 1 } }
$tools = Join-Path $env:LOCALAPPDATA "btp-tools"
$jdk = (Get-ChildItem (Join-Path $tools "jdk") -Directory | Select-Object -First 1).FullName
$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:PATH = (Join-Path $tools "flutter\flutter\bin") + ";" + (Join-Path $jdk "bin") + ";" + $env:PATH
$env:PUB_CACHE = Join-Path $tools "pub-cache"
$repo = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$build = Join-Path $env:TEMP "btp-apkbuild"
$url = "https://bengaluru-transit-planner-v4.onrender.com/"
$label = "Bengaluru Transit"

if (-not (Test-Path $build)) { Copy-Item (Join-Path $repo "android\flutter_app") $build -Recurse }
Set-Location $build
flutter --version
flutter config --no-analytics | Out-Null
flutter config --android-sdk $env:ANDROID_HOME | Out-Null
if (-not (Test-Path "android")) {
  flutter create --platforms=android --project-name bmtc_planner_app --org io.github.upendra8690 .; Step 'flutter create'
  if (Test-Path "test") { Remove-Item "test" -Recurse -Force -Confirm:$false }
}
$manifest = "android\app\src\main\AndroidManifest.xml"
$m = Get-Content $manifest -Raw
foreach ($perm in "INTERNET", "ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION") {
  if ($m -notmatch "android.permission.$perm") { $m = $m -replace "<application", "<uses-permission android:name=`"android.permission.$perm`" />`n    <application" }
}
$m = $m -replace 'android:label="[^"]*"', "android:label=`"$label`""
if ($m -notmatch "android:allowBackup") { $m = $m -replace "<application", '<application android:allowBackup="false" android:fullBackupContent="false"' }
[IO.File]::WriteAllText((Resolve-Path $manifest), $m)
$gradle = "android\app\build.gradle.kts"
$g = Get-Content $gradle -Raw
$g = [regex]::Replace($g, '(compileSdk|targetSdk) = flutter\.(compileSdkVersion|targetSdkVersion)', '$1 = maxOf(flutter.$2, 36)')
[IO.File]::WriteAllText((Resolve-Path $gradle), $g)
Select-String -Path $gradle -Pattern "compileSdk|targetSdk"

flutter pub add --dev flutter_launcher_icons flutter_native_splash; Step 'pub add'
@"
flutter_launcher_icons:
  android: true
  ios: false
  image_path: "assets/icon/icon.png"
  adaptive_icon_background: "assets/icon/background.png"
  adaptive_icon_foreground: "assets/icon/foreground.png"
"@ | Set-Content -Encoding utf8 flutter_launcher_icons.yaml
@"
flutter_native_splash:
  color: "#0b47a8"
  image: assets/icon/foreground.png
  android_12:
    color: "#0b47a8"
    image: assets/icon/foreground.png
  ios: false
  web: false
"@ | Set-Content -Encoding utf8 flutter_native_splash.yaml
flutter pub get; Step 'pub get'
dart run flutter_launcher_icons; Step 'icons'
dart run flutter_native_splash:create; Step 'splash'
flutter analyze --no-fatal-infos
flutter build apk --release --build-number=1 --dart-define=PLANNER_URL=$url; Step 'build apk'
Get-Item "build\app\outputs\flutter-apk\app-release.apk" | Select-Object FullName, Length
"BUILD DONE"
