"""Emulator test of the Android test APK (Android 36 emulator, x86_64, Google APIs image). Not a physical device.

usage: python tests/android/emulator_check.py <apk> <out-dir>   (emulator-5554 must be booted)
Drives the app through adb: UI text comes from uiautomator dumps (the WebView's accessibility tree), taps go to the
centre of the matching node, and every step saves a screenshot.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
import time
from pathlib import Path

ADB = str(Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe")
PKG = "io.github.upendra8690.bmtc_planner_app"
APK, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def adb(*args: str, timeout: int = 120) -> str:
    return subprocess.run([ADB, "-s", "emulator-5554", *args], capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace").stdout


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f": {detail[:200]}"), flush=True)


def shot(name: str) -> None:
    data = subprocess.run([ADB, "-s", "emulator-5554", "exec-out", "screencap", "-p"], capture_output=True,
                          timeout=60).stdout
    (OUT / f"{len(list(OUT.glob('*.png'))) + 1:02d}-{name}.png").write_bytes(data)


def dump() -> list[tuple[str, tuple[int, int, int, int]]]:
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    xml = adb("shell", "cat", "/sdcard/ui.xml")
    nodes = []
    node = re.compile(r'<node [^>]*?text="([^"]*)"[^>]*?content-desc="([^"]*)"[^>]*?'
                      r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')
    for m in node.finditer(xml):
        label = (m.group(1) or m.group(2)).replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
        nodes.append((label, tuple(int(m.group(i)) for i in range(3, 7))))
    return nodes


def screen_text() -> str:
    return "\n".join(label for label, _ in dump())


def wait_for(text: str, timeout: float = 90) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if text.lower() in screen_text().lower():
            return True
        time.sleep(2)
    return False


def tap_text(text: str, exact: bool = False, last: bool = False) -> bool:
    matches = [b for label, b in dump() if (label.strip() == text if exact else text.lower() in label.lower())]
    if not matches:
        return False
    x1, y1, x2, y2 = matches[-1] if last else matches[0]
    adb("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
    time.sleep(1.5)
    return True


def focused() -> str:
    out = adb("shell", "dumpsys", "window")
    m = re.search(r"mCurrentFocus=Window\{[^ ]+ [^ ]+ ([^}]+)\}", out)
    return m.group(1) if m else ""


def launch() -> None:
    adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(3)


# ---------------------------------------------------------------- install and first start
print(adb("install", "-r", APK, timeout=300).strip()[-80:])
adb("shell", "pm", "clear", PKG)
adb("shell", "settings", "put", "global", "window_animation_scale", "0")
adb("shell", "settings", "put", "global", "transition_animation_scale", "0")
version = adb("shell", "dumpsys", "package", PKG)
check("The APK installs (targetSdk 36)", "targetSdk=36" in version, re.findall(r"targetSdk=\d+", version)[:1])
launch()
loaded = wait_for("Service notices", 150)  # the free server may need up to a minute to wake
shot("home")
check("The app opens the live v4 planner (Home with service notices)", loaded, screen_text()[:300])
text = screen_text()
check("The app says it is independent and not an official BMTC app",
      "Not an official BMTC" in text or "not affiliated" in text.lower() or "Independent" in text)

# ---------------------------------------------------------------- navigation
for tab, expect in (("Plan", "Plan a journey"), ("Metro", "Metro"), ("Nearby", "near"), ("More", "Administration"),
                    ("Home", "Service notices")):
    tapped = tap_text(tab, exact=True, last=True)
    ok = tapped and wait_for(expect, 30)
    shot("nav-" + tab.lower())
    check(f"Bottom navigation: {tab}", ok, screen_text()[:200])

# ---------------------------------------------------------------- maps
check("The Home map draws (OpenStreetMap credit shown)", wait_for("OpenStreetMap", 30))

# ---------------------------------------------------------------- journey planning (on a date: Metro may be closed)
tap_text("Plan", exact=True, last=True)
wait_for("Plan a journey", 30)
tap_text("Unverified feed")
time.sleep(1)
tap_text("From", exact=True)
adb("shell", "input", "text", "Majestic")
adb("shell", "input", "keyevent", "61")  # tab to the next field
adb("shell", "input", "text", "Indiranagar")
adb("shell", "input", "keyevent", "111")  # escape: close the keyboard
tap_text("On a date")
tap_text("Plan journey", exact=True) or tap_text("Find journeys") or tap_text("Plan", last=False)
planned = wait_for("min", 60)
shot("journey")
check("Journey planning returns options between two Metro stations", planned and "Majestic" in screen_text(),
      screen_text()[:300])

# ---------------------------------------------------------------- location permission
adb("emu", "geo", "fix", "77.5970", "12.9810")
adb("shell", "pm", "revoke", PKG, "android.permission.ACCESS_FINE_LOCATION")
adb("shell", "pm", "revoke", PKG, "android.permission.ACCESS_COARSE_LOCATION")
tap_text("Use my location")
asked = wait_for("location", 15) and ("Allow" in screen_text() or "While using" in screen_text())
shot("location-prompt")
check("Location is asked only when the passenger taps 'Use my location'", asked, screen_text()[:300])
tap_text("While using the app") or tap_text("Only this time") or tap_text("Allow")
filled = wait_for("Cubbon Park", 40)
shot("location-filled")
check("After allowing, the nearest station (Cubbon Park) is filled", filled, screen_text()[:300])

# ---------------------------------------------------------------- back button
tap_text("Metro", exact=True, last=True)
wait_for("Metro", 20)
adb("shell", "input", "keyevent", "4")
time.sleep(2)
stayed = PKG in focused()
shot("after-back")
check("Back returns to the previous screen inside the app", stayed and "Plan a journey" in screen_text(),
      focused() + " | " + screen_text()[:150])

# ---------------------------------------------------------------- external links
tap_text("More", exact=True, last=True)
wait_for("Official", 20)
tap_text("Official services") or tap_text("Official links") or tap_text("Official")
time.sleep(2)
link = tap_text("mybmtc") or tap_text("bmrc.co.in") or tap_text("Official website") or tap_text("Website")
time.sleep(5)
outside = PKG not in focused()
shot("external-link")
check("Official links open outside the app (in the browser)", link and outside, focused())
adb("shell", "input", "keyevent", "4")
time.sleep(2)
launch()

# ---------------------------------------------------------------- screen sizes
for size, density in (("720x1280", "320"), ("1080x2400", "420"), ("1600x2560", "320")):
    adb("shell", "wm", "size", size)
    adb("shell", "wm", "density", density)
    time.sleep(3)
    tap_text("Home", exact=True, last=True)
    ok = wait_for("Service notices", 30)
    shot(f"size-{size}")
    check(f"Home renders at {size} ({density} dpi)", ok)
adb("shell", "wm", "size", "reset")
adb("shell", "wm", "density", "reset")
time.sleep(2)

# ---------------------------------------------------------------- app restart
adb("shell", "am", "force-stop", PKG)
launch()
check("After a force stop the app starts again", wait_for("Service notices", 120))
shot("restart")

# ---------------------------------------------------------------- offline and error handling
tap_text("Metro", exact=True, last=True)
wait_for("Metro", 20)
adb("shell", "svc", "wifi", "disable")
adb("shell", "svc", "data", "disable")
time.sleep(4)
tap_text("Home", exact=True, last=True)
offline_banner = wait_for("offline", 20)
shot("offline-in-app")
check("Offline: the app keeps working from its saved shell and says it is offline", offline_banner, screen_text()[:300])
adb("shell", "am", "force-stop", PKG)
adb("shell", "pm", "clear", PKG)  # no saved copy: a cold start offline must show the retry screen, not a blank page
launch()
retry = wait_for("Try again", 40) or wait_for("Retry", 5)
shot("offline-cold-start")
check("Offline cold start shows a clear error with a retry button", retry, screen_text()[:300])
adb("shell", "svc", "wifi", "enable")
adb("shell", "svc", "data", "enable")
time.sleep(6)
tap_text("Try again") or tap_text("Retry")
check("Retry after the network returns loads the planner", wait_for("Service notices", 150))
shot("after-retry")

# ---------------------------------------------------------------- sign-in (accounts are off on the public service)
tap_text("More", exact=True, last=True)
wait_for("My account", 20)
tap_text("My account")
account = wait_for("permanent database", 30) or wait_for("switched off", 5)
shot("account")
check("Account screen on the public service explains that sign-in needs a permanent database", account,
      screen_text()[:300])

passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{len(results)} passed on {dt.date.today()} (Android emulator, API 36, x86_64)")
(OUT / "results.txt").write_text("\n".join(("PASS " if ok else "FAIL ") + name + ("" if ok else f": {d}")
                                           for name, ok, d in results) + f"\n{passed}/{len(results)} passed\n",
                                 encoding="utf-8")
