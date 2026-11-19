"""The app's icons come from the owner's logo (assets/brand/logo-source.png) through scripts/make_brand_icons.py.

These check every size the PWA, browsers and Android need, that maskable and adaptive icons keep the artwork away
from the edges, and that the brand stays independent: no operator logo and the unofficial statement kept.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}


def image(rel: str) -> Image.Image:
    return Image.open(ROOT / rel)


@pytest.mark.parametrize(("rel", "size"), [
    ("dashboard/icons/icon-192.png", 192), ("dashboard/icons/icon-512.png", 512),
    ("dashboard/icons/icon-maskable-512.png", 512), ("dashboard/icons/apple-touch-icon-180.png", 180),
    ("dashboard/icons/favicon-32.png", 32), ("assets/brand/play-store-icon-512.png", 512),
    ("android/flutter_app/assets/icon/icon.png", 1024), ("android/flutter_app/assets/icon/foreground.png", 1024),
    ("android/flutter_app/assets/icon/background.png", 1024),
])
def test_each_icon_has_its_size(rel, size):
    assert image(rel).size == (size, size)


def test_rounded_icons_have_transparent_corners_and_square_ones_none():
    rounded = ("dashboard/icons/icon-192.png", "dashboard/icons/icon-512.png",
               "android/flutter_app/assets/icon/icon.png")
    for rel in rounded:
        icon = image(rel).convert("RGBA")
        assert icon.getpixel((0, 0))[3] == 0, rel
        assert icon.getpixel((icon.width // 2, icon.height // 2))[3] == 255, rel
    for rel in ("dashboard/icons/icon-maskable-512.png", "dashboard/icons/apple-touch-icon-180.png",
                "assets/brand/play-store-icon-512.png", "android/flutter_app/assets/icon/background.png"):
        assert image(rel).mode == "RGB", f"{rel} must be opaque: launchers and stores apply their own mask"


def test_adaptive_and_maskable_artwork_stays_inside_the_safe_zone():
    foreground = image("android/flutter_app/assets/icon/foreground.png").convert("RGBA")
    box = foreground.getbbox()
    width = box[2] - box[0]
    assert width <= foreground.width * 0.67, "the adaptive foreground must fit the 66 dp safe circle"
    assert foreground.getpixel((10, 10))[3] == 0


def test_every_android_density_is_present():
    for name, factor in DENSITIES.items():
        folder = f"android/launcher_icons/mipmap-{name}"
        legacy, adaptive = round(48 * factor), round(108 * factor)
        assert image(f"{folder}/ic_launcher.png").size == (legacy, legacy)
        assert image(f"{folder}/ic_launcher_round.png").size == (legacy, legacy)
        assert image(f"{folder}/ic_launcher_foreground.png").size == (adaptive, adaptive)
        assert image(f"{folder}/ic_launcher_background.png").size == (adaptive, adaptive)
    assert "ic_launcher_background" in (ROOT / "android/launcher_icons/values/ic_launcher_background.xml").read_text()


def test_the_favicon_file_carries_three_sizes():
    with Image.open(ROOT / "dashboard/favicon.ico") as ico:
        assert {(16, 16), (32, 32), (48, 48)} <= set(ico.info.get("sizes", set()))


def test_the_manifest_names_the_independent_app_and_lists_its_icons():
    manifest = json.loads((ROOT / "dashboard/manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == "Bengaluru Transit Planner"
    sources = {i["src"]: i.get("purpose") for i in manifest["icons"]}
    assert sources == {"/icons/icon-192.png": "any", "/icons/icon-512.png": "any",
                       "/icons/icon-maskable-512.png": "maskable"}
    page = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
    assert "Not an official BMTC or BMRCL app" in page


def test_the_brand_record_states_independence():
    record = (ROOT / "assets/brand/README.md").read_text(encoding="utf-8")
    assert "not the BMTC logo" in record
    assert "does not imply" in record
