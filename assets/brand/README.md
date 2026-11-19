# Brand: Bengaluru Transit Planner

- **Name:** Bengaluru Transit Planner. The short name is "BLR Transit".
- **Logo:** `logo-source.png` (1254 × 1254 px), the owner's own blue-and-cyan transit logo, supplied on 20 Nov 2026.
- **Not an operator logo:** this is not the BMTC logo, nor the logo of BMRCL, Namma Metro or the Government of
  Karnataka, and it does not imply any affiliation or endorsement. The app is independent. It keeps saying so on the
  splash screen ("Independent app. Not an official BMTC or BMRCL app."), on Home and in `/api/meta`.

## Generated files
`scripts/make_brand_icons.py` makes every icon from `logo-source.png`. Run it again after the logo changes, then bump
the service worker cache version in `dashboard/sw.js`.

| File | Use |
|---|---|
| `dashboard/icons/icon-192.png`, `icon-512.png` | PWA icons ("any"), rounded with transparent corners; also the splash logo |
| `dashboard/icons/icon-maskable-512.png` | PWA maskable icon. The artwork sits inside the safe zone on the logo's own blues |
| `dashboard/icons/apple-touch-icon-180.png` | iPhone and iPad home screen (opaque) |
| `dashboard/icons/favicon-32.png`, `dashboard/favicon.ico` (16, 32 and 48 px) | Browser tabs |
| `android/flutter_app/assets/icon/icon.png`, `foreground.png`, `background.png` | Sources that CI turns into launcher icons and the native splash (flutter_launcher_icons, flutter_native_splash) |
| `android/launcher_icons/mipmap-*/` | Every Android density for review. Legacy and round icons at 48, 72, 96, 144 and 192 px; adaptive foreground and background at 108, 162, 216, 324 and 432 px |
| `play-store-icon-512.png` | Google Play listing icon (opaque, 512 px) |
| `app-icon-full-1024.png`, `app-icon-rounded-1024.png` | Masters for documents and listings |

## A point for the owner to decide
The logo shows a building silhouette that resembles **Vidhana Soudha**, the seat of the Karnataka legislature. It is
a well-known Bengaluru landmark, but next to transport services some viewers could read it as a sign of government
backing. That would conflict with the rule that the app must not imply government affiliation. It is used here
because the owner supplied this logo. If an official body raises it, use a version without the building (for
example the bus and route only).
