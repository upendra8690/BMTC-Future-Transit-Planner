# API and data integration register

Research date: 16 November 2026, from web searches. No integration below has been confirmed with its operator.
"Production use allowed" means the operator's terms clearly permit it; "Unknown" means we must not ship it as a
production dependency until it is confirmed in writing.

Every integration is built behind an adapter with three states, shown to users and admins:
`DISABLED` (no permission or credentials; the reason is shown), `DEMO` (synthetic data, labelled), `ACTIVE` (authorised and verified).

The licence and status of each **dataset** is tracked in `DATA_SOURCE_REGISTER.md`; this file covers services and
access routes.

## 0. Additions for the 4.0 master brief

| Integration | Operator | Permission / requirement | Cost | Status |
|---|---|---|---|---|
| BMTC real-time data for aggregators | BMTC (reported by [Construction World](https://www.constructionworld.in/amp/transport-infrastructure/highways-and-roads-infrastructure/bmtc-to-share-real-time-bus-data-with-aggregators/97367)) | Application and data-sharing agreement; terms unknown | Unknown | Blocked; the owner may enquire |
| Email (password reset, account notices) | A transactional email provider with a free tier (for example Brevo or Resend; check current terms) | Account, verified sender domain or address; API key kept server-side | Free tier (limits apply) | Planned for Phase 5; owner chooses |
| Indian Railways, airport, cabs, hotels, temple bookings | Each operator's official website | Linking only; no scraping or automated booking | Free | Planned as links (Phase 8) |
| Traffic / road disruptions | Bengaluru Traffic Police announcements; commercial traffic APIs | Official feed not identified; commercial APIs paid | Paid or unavailable | Unavailable |
| Apple App Store (native iOS) | Apple | Apple Developer Program, a Mac with Xcode | Paid (annual) | Unavailable at ₹0; iPhone users use the PWA |
| Google Play (AAB) | Google | Developer account; store policies on naming and affiliation | One-time US$25 | Optional |

## 1. Transit data

### 1.1 BMTC + BMRCL static GTFS via DULT Transport Data Hub
| Field | Finding |
|---|---|
| Operator | Directorate of Urban Land Transport (DULT), Government of Karnataka, with BMTC and BMRCL |
| Evidence | June 2024 announcement that BMTC and BMRCL would publish GTFS on a public portal ([Deccan Herald](https://www.deccanherald.com/india/karnataka/bengaluru/in-historic-first-namma-metro-bmtc-open-up-their-data-to-help-public-transport-users-in-bengaluru-3160955)); later coverage of planners built on it ([Deccan Herald](https://www.deccanherald.com/india/karnataka/bengaluru/now-plan-metro-bus-and-last-mile-journeys-in-bengaluru-with-a-single-tap-3624689)). Portal address reported as `tdh.dult-karnataka.com`. |
| Officially permitted? | Probably, but the licence text was not found |
| Terms / licence | **Unknown** |
| Authentication | Unknown (possibly registration) |
| Rate limits | Unknown |
| Privacy | None (schedule data) |
| Commercial use | Unknown |
| Reliability | Unknown update frequency |
| Failure handling | Importer rejects bad feeds and keeps the last good one |
| **Status** | **Action for you:** open the portal in a browser, register if required, download the feed, and save the licence/terms page. Then the admin imports it as kind `OFFICIAL` and verifies it with that evidence. |

### 1.2 BMTC GTFS-Realtime (vehicle positions, trip updates)
| Field | Finding |
|---|---|
| Operator | BMTC |
| Evidence | 2024 announcement said realtime would follow static data. No public endpoint found in 2026 searches. |
| **Status** | **Blocked.** Adapter will be built and tested with recorded sample files; it stays `DISABLED`. Live positions are never shown without it. |

### 1.3 Community feeds (research leads only)
| Feed | Origin | Licence / risk | Use |
|---|---|---|---|
| `github.com/Vonter/bmtc-gtfs` | Generated from Namma BMTC app data (its README calls it unofficial) | Origin of data not authorised; terms unclear | Do not use in production. Allowed only for local testing if you accept the risk. |
| `github.com/Vonter/bmrcl-gtfs` | Built from OpenStreetMap + BMRCL timetable images ([Datameet post](https://groups.google.com/g/datameet/c/h5uI8DMlgi4)) | OSM part is ODbL (attribution + share-alike); BMRCL timetable reuse terms unknown | Candidate for a clearly labelled `UNVERIFIED_FEED` Metro feed **after** checking the repo's licence file. |
| Kaggle "BMTC GTFS Dataset" ([link](https://www.kaggle.com/datasets/anikets95/bmtc-gtfs-dataset/data)) | Says it comes from a BMTC-hosted API "in an unofficial capacity" | Unauthorised origin | Do not use. |
| `iotakodali/bmtc-realtime-api` | Unofficial ETA API | CC BY-NC-SA 4.0 (no commercial use), unofficial | Do not use. |
| Namma BMTC app's internal API | Private API of the official app | Not authorised | **Never use.** Reverse-engineered endpoints are off-limits. |

## 2. Tickets and payments

### 2.1 Metro QR tickets via ONDC
| Field | Finding |
|---|---|
| Operator | BMRCL, through the ONDC mobility network |
| Evidence | Since July 2025, Namma Metro QR tickets are sold through ONDC on nine third-party apps (Namma Yatri, Rapido, redBus, Tummoc and others) ([The Week](https://www.theweek.in/wire-updates/national/2025/07/08/srg8-ka-metro-tickets.html), [Deccan Herald](https://www.deccanherald.com/india/karnataka/bengaluru/now-namma-metro-tickets-available-on-nine-mobile-apps-3621119)). Mobile QR passes launched in the official app in January 2026 ([Trayaan](https://www.trayaan.com/2026/01/bmrcl-launches-mobile-qr-based-unlimited-travel-passes-for-bengaluru-metro-trains.html)). |
| Officially permitted? | Yes, for apps registered on ONDC as buyer apps |
| Requirements | Registered legal entity, ONDC participant onboarding and compliance, payment collection setup |
| Cost | Not ₹0 (company registration, compliance, payment gateway) |
| **Status** | **Blocked.** Build the ticket UI states and a provider interface; until then show "Buy Metro tickets in the Namma Metro app, WhatsApp 8105556677, or ONDC apps" with official links. |

### 2.2 BMTC bus tickets and passes
| Field | Finding |
|---|---|
| Evidence | Press reports say bus tickets are also sold via apps such as Namma Yatri and Tummoc ([Inc42](https://inc42.com/buzz/now-bengaluru-metro-bus-commuters-can-buy-tickets-via-namma-yatri-tummoc-apps)); the integration path was not confirmed |
| **Status** | **Blocked.** Needs a written agreement with BMTC or an ONDC route. Same disabled-state design. |

### 2.3 Payment gateway (UPI, cards)
| Field | Finding |
|---|---|
| Options | Razorpay, Cashfree, PhonePe PG and similar |
| Requirements | Merchant KYC (business or sole-proprietor documents), bank account, website policies |
| Wallet | A stored-value wallet needs an RBI prepaid payment instrument licence. **Not planned.** |
| **Status** | **Blocked.** Payment code is designed (webhook signature checks, idempotency keys, no card/UPI data stored) and tested only against a fake gateway in tests. Never active in production without a gateway agreement. |

### 2.4 NCMC
| Field | Finding |
|---|---|
| Operator | Issuing banks under NPCI's RuPay NCMC programme |
| **Status** | Information module only (Planned). Card issue, top-up or reading needs bank/NPCI integration and hardware: **out of scope.** |

## 3. Maps, location and notifications

| Service | Terms that matter | Cost | Plan |
|---|---|---|---|
| OpenStreetMap standard tiles | Tile usage policy: attribution required; heavy or app traffic not allowed | Free for light use | Default for the demo; tile URL configurable; switch when usage grows |
| Free-tier tile providers (MapTiler, Stadia, Thunderforest) | API key; monthly limits | Free tier | Key kept server-side or domain-restricted |
| Nominatim geocoding | Max 1 request/second; no autocomplete; attribution | Free | Server-side, cached, debounced; or Photon self-hosted later |
| OSM facilities data (toilets, water, parking) | ODbL: attribution, share-alike for derived databases | Free | Import with attribution |
| Browser Geolocation | User permission, HTTPS | Free | Ask only on "Near me"; never stored server-side |
| Web Push (VAPID) | Browser permission | Free | Notifications for the PWA |
| Firebase Cloud Messaging | Google account; terms | Free | Only if the native app needs push |
| SMS / WhatsApp (OTP, SOS alerts) | Paid per message; DLT registration in India for SMS | **Paid** | Not planned; SOS uses the phone dialler (`tel:112`) and share-location instead |

## 4. AI

| Service | Terms | Cost | Plan |
|---|---|---|---|
| Rule-based assistant | — | Free | Default: answers only from the app's own APIs |
| Claude API or other LLM | API key, usage pricing | **Paid** | Optional adapter, off by default; key only on the server; answers must cite app data |

## 5. Hosting and storage

| Service | Free-tier limits (check current terms) | Use |
|---|---|---|
| Render web service | Sleeps when idle; 512 MB RAM; disk wiped on restart | Current demo host |
| Render Postgres (free) | Expires after a limited period | Not recommended for accounts |
| Neon Postgres (free) | Small storage quota; persistent | Recommended for accounts (needs your sign-up) |
| GitHub Actions | Free minutes for public repos | CI, APK builds |
