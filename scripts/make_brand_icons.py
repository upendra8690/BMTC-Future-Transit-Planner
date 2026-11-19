#!/usr/bin/env python3
"""Make every app icon from the owner's logo (assets/brand/logo-source.png). Run again after the logo changes.

  python scripts/make_brand_icons.py

The source is a blue rounded square on a black corner background. Three versions are derived:
- "rounded": the rounded square with transparent corners (PWA "any" icons, favicon, splash, legacy launcher icon);
- "full": the same artwork with the corners filled with the logo's own edge blue (Apple touch icon, Play Store icon);
- "safe": the full version scaled into the centre of a canvas of the edge blue, so that circle and squircle masks never
  cut the artwork (PWA maskable icon, Android adaptive icon foreground and its background colour).

Outputs:
- dashboard/icons: icon-192, icon-512, icon-maskable-512, apple-touch-icon-180 and favicon-32 (PNG).
- dashboard/favicon.ico: 16, 32 and 48 px.
- android/flutter_app/assets/icon: icon.png, foreground.png and background.png, which CI turns into launcher icons
  with flutter_launcher_icons.
- android/launcher_icons: every Android density for review. Legacy ic_launcher and ic_launcher_round are 48, 72, 96,
  144 and 192 px; the adaptive foreground is 108, 162, 216, 324 and 432 px.
- assets/brand: play-store-icon-512.png and the full and rounded masters at 1024 px.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "brand" / "logo-source.png"
DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
SAFE_SCALE = 0.66  # adaptive icon foreground: keep the artwork inside the 66 dp safe circle


def rounded_mask(size: int, box: tuple[int, int, int, int], radius: int, scale: int = 4) -> Image.Image:
    """An anti-aliased mask of a rounded square (drawn large, then reduced)."""
    big = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(big).rounded_rectangle([v * scale for v in box], radius=radius * scale, fill=255)
    return big.resize((size, size), Image.LANCZOS)


def extend_colours(image: Image.Image, mask: Image.Image, work: int = 160) -> Image.Image:
    """Fills the area outside the mask with a smooth continuation of the colours inside (a normalised blur)."""
    small = image.resize((work, work), Image.LANCZOS)
    alpha = mask.resize((work, work), Image.LANCZOS)
    premultiplied = Image.composite(small, Image.new("RGB", (work, work), 0), alpha)
    radius = work * 0.12
    blurred = premultiplied.filter(ImageFilter.GaussianBlur(radius))
    weight = alpha.filter(ImageFilter.GaussianBlur(radius))
    out = Image.new("RGB", (work, work))
    pixels, weights, target = blurred.load(), weight.load(), out.load()
    for y in range(work):
        for x in range(work):
            w = max(weights[x, y], 1) / 255
            target[x, y] = tuple(min(255, round(c / w)) for c in pixels[x, y])
    return out.resize(image.size, Image.LANCZOS)


def main() -> int:
    source = Image.open(SOURCE).convert("RGB")
    size = min(source.size)
    source = source.crop((0, 0, size, size))
    # The logo's own shape: its blue square, without the dark rim, with a soft anti-aliased edge.
    blue = source.split()[2]
    mask = blue.point(lambda v: 255 if v > 70 else 0)
    mask = mask.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.GaussianBlur(1.4))
    box = mask.getbbox()

    rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded.paste(source, (0, 0), mask)
    rounded = rounded.crop(box).resize((1024, 1024), Image.LANCZOS)

    full = Image.composite(source, extend_colours(source, mask), mask).crop(box).resize((1024, 1024), Image.LANCZOS)
    edge = full.resize((1, 1), Image.LANCZOS).getpixel((0, 0))

    def field(canvas: int) -> Image.Image:
        """A soft blue background in the logo's own colours, for the space around a scaled-down logo."""
        soft = full.resize((canvas, canvas), Image.LANCZOS).filter(ImageFilter.GaussianBlur(canvas * 0.22))
        return soft.convert("RGBA")

    def safe(canvas: int, scale: float, transparent: bool) -> Image.Image:
        image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0)) if transparent else field(canvas)
        inner = round(canvas * scale)
        logo = rounded.resize((inner, inner), Image.LANCZOS)
        image.alpha_composite(logo, ((canvas - inner) // 2, (canvas - inner) // 2))
        return image

    icons = ROOT / "dashboard" / "icons"
    rounded.resize((192, 192), Image.LANCZOS).save(icons / "icon-192.png", optimize=True)
    rounded.resize((512, 512), Image.LANCZOS).save(icons / "icon-512.png", optimize=True)
    safe(512, 0.82, transparent=False).convert("RGB").save(icons / "icon-maskable-512.png", optimize=True)
    full.resize((180, 180), Image.LANCZOS).save(icons / "apple-touch-icon-180.png", optimize=True)
    rounded.resize((32, 32), Image.LANCZOS).save(icons / "favicon-32.png", optimize=True)
    rounded.save(ROOT / "dashboard" / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    flutter = ROOT / "android" / "flutter_app" / "assets" / "icon"
    rounded.save(flutter / "icon.png", optimize=True)
    safe(1024, SAFE_SCALE, transparent=True).save(flutter / "foreground.png", optimize=True)
    field(1024).convert("RGB").save(flutter / "background.png", optimize=True)

    launcher = ROOT / "android" / "launcher_icons"
    circle = rounded_mask(1024, (0, 0, 1023, 1023), 512)
    round_icon = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    round_icon.paste(safe(1024, 0.86, transparent=False), (0, 0), circle)
    for name, factor in DENSITIES.items():
        folder = launcher / f"mipmap-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        legacy = round(48 * factor)
        rounded.resize((legacy, legacy), Image.LANCZOS).save(folder / "ic_launcher.png", optimize=True)
        round_icon.resize((legacy, legacy), Image.LANCZOS).save(folder / "ic_launcher_round.png", optimize=True)
        adaptive = round(108 * factor)
        safe(adaptive, SAFE_SCALE, transparent=True).save(folder / "ic_launcher_foreground.png", optimize=True)
        field(adaptive).convert("RGB").save(folder / "ic_launcher_background.png", optimize=True)
    (launcher / "values").mkdir(exist_ok=True)
    (launcher / "values" / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        f'    <color name="ic_launcher_background">#{edge[0]:02X}{edge[1]:02X}{edge[2]:02X}</color>\n</resources>\n',
        encoding="utf-8", newline="\n")

    brand = ROOT / "assets" / "brand"
    full.resize((512, 512), Image.LANCZOS).save(brand / "play-store-icon-512.png", optimize=True)
    full.save(brand / "app-icon-full-1024.png", optimize=True)
    rounded.save(brand / "app-icon-rounded-1024.png", optimize=True)
    full.save(ROOT / "assets" / "app-icon-master-1024.png", optimize=True)
    print(f"average colour #{edge[0]:02X}{edge[1]:02X}{edge[2]:02X}; logo square {box}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
