# Feature matrix for 4.0

Status values: **Done** (works and is tested), **Partial** (some parts work), **Planned** (buildable with free tools,
not started), **Blocked** (needs a permission, credential, partner or payment that does not exist yet).
A screen existing does not make a feature Done.

Legend for data source: GTFS = static GTFS feed; RT = GTFS-Realtime; OSM = OpenStreetMap; — = none needed.

## Bus: routes, stops, timetables, fares

| Feature | Existing (3.0) | Missing | Backend | Frontend | Data source | Permission needed | Tests | Status |
|---|---|---|---|---|---|---|---|---|
| Route search by number/name | `/api/routes?q=` | Ranking, fuzzy match | Better scoring | Search bar on home | GTFS | Feed licence | Search tests exist | Done |
| Routes by origin/destination | `/api/plan` finds them | Dedicated "routes between" list | Query over trips | Results list | GTFS | Feed licence | New | Partial |
| Direction + stop sequence | Route detail | — | — | Mobile layout | GTFS | Feed licence | Exist | Done |
| Route map | Leaflet polyline from shapes | Mobile-sized map | — | Redesign | GTFS shapes + tiles | Tile terms | Browser checks | Done |
| Timetable, service days | Timetable + CSV | Stop-wise timetable view | Extend stop departures | New view | GTFS | Feed licence | Exist + new | Partial |
| Fare info / calculator | One-ride fares from GTFS | Multi-ride totals, zone fares, breakdown UI | Zone fare rules, totals | Fare calculator screen | GTFS fares | Official fare table | Fare tests exist | Partial |
| Favourite routes | Saved routes (per device) | Account sync | Users + favourites | Favourites screen | — | — | Exist | Partial |
| Share route | — | Share links | Deep-link URLs | Web Share API | — | — | New | Planned |
| Data last-updated date | Feed dates shown | Visible "updated on" everywhere | Expose import date | Badges | GTFS | — | New | Partial |

## Nearby stops and maps

| Feature | Existing | Missing | Backend | Frontend | Data source | Permission | Tests | Status |
|---|---|---|---|---|---|---|---|---|
| Nearby stops by location | `/api/stops/nearby` | Mobile map-first UI | — | Home map | GTFS | Location (user, on demand) | Exist | Partial |
| Routes serving a stop | Departures list | Route list per stop | Query | Stop sheet | GTFS | — | New | Partial |
| Scheduled vs live labels | All times "scheduled" | Live badge when RT exists | RT adapter | Badges | RT | Agency RT feed | New | Partial |
| Map filters (bus/metro/facilities) | — | Layers | Feature APIs | Layer toggles | GTFS, OSM | Tile terms | New | Planned |
| Destination search (geocoding) | Stop-name search only | Place search | Geocoder adapter | Search | Nominatim/other | Geocoder terms (rate limits) | New | Planned |

## Live tracking

| Feature | Existing | Missing | Backend | Frontend | Data source | Permission | Tests | Status |
|---|---|---|---|---|---|---|---|---|
| Bus positions on map | — | Everything | GTFS-RT ingestion adapter, freshness rules | Live markers | BMTC GTFS-RT | **No public BMTC RT feed found** | Stale/absent data tests | Blocked (adapter Planned) |
| Live ETA | — | Everything | From RT trip updates only | ETA badges | RT | Same | Same | Blocked |
| Vehicle number search | — | Everything | Needs RT vehicle descriptors | Search | RT | Same + privacy review | — | Blocked |

## Journey planner

| Feature | Existing | Missing | Backend | Frontend | Data source | Permission | Tests | Status |
|---|---|---|---|---|---|---|---|---|
| Bus journeys, 0–2 changes | RAPTOR | — | — | Mobile results | GTFS | Feed licence | Planner + mutation tests | Done |
| Walking connections | Between stops ≤300 m | Walk from origin point | Access legs | Map | GTFS + coordinates | — | New | Partial |
| Metro-only / bus+Metro | Works if Metro feed imported (same classification) | Mode filter, station transfers | Mode filters, `transfers.txt` | Mode chips | Metro GTFS | **Metro feed licence** | New | Blocked on data (code Planned) |
| Alternatives, durations, transfers | Yes | — | — | Redesign | GTFS | — | Exist | Done |
| Fare breakdown per leg | One-ride only | Per-leg + total | Fare engine | Breakdown | GTFS fares | Official fares | New | Partial |
| Accessibility info | — | `wheelchair_boarding` etc. | Import fields | Icons | GTFS | — | New | Planned |
| Save / share journeys | — | Everything | Saved journeys | Buttons | — | Accounts (D-DB) | New | Planned |

## Namma Metro

| Feature | Existing | Missing | Backend | Frontend | Data source | Permission | Tests | Status |
|---|---|---|---|---|---|---|---|---|
| Station directory, lines, interchanges | — | Everything | Stations from GTFS `location_type=1`, line colours | Metro screen | Metro GTFS | **Licence of Metro feed** | New | Blocked on data (code Planned) |
| Station-to-station planner | Planner can do it | Station search | — | Metro planner | Metro GTFS | Same | New | Blocked on data |
| Metro timetable / fares | — | — | Same tables | Views | Metro GTFS fares | Same | New | Blocked on data |
| Last-mile bus connections | Cross-feed walking transfers | Station↔stop links | Transfers | UI | Both feeds | Both licences | New | Blocked on data |
| Metro QR tickets | — | Everything | ONDC buyer-app integration | Ticket screens | ONDC network | **ONDC registration as a buyer app (registered business)** | Payment/ticket state tests | Blocked |

## Tickets, passes, payments, NCMC

| Feature | Existing | Missing | Backend | Frontend | Data source | Permission | Tests | Status |
|---|---|---|---|---|---|---|---|---|
| Bus tickets / passes | — | Everything | Provider adapter (disabled) | "Not available" + where to buy | Authorised provider | **BMTC or ONDC agreement** | Disabled-state tests | Blocked |
| Payments (UPI, cards, wallets) | — | Everything | Gateway adapter, webhooks, idempotency | Status screens | Gateway | **Gateway merchant KYC (business)**; wallet needs RBI PPI licence | Webhook/duplicate tests (with fake gateway in tests only) | Blocked |
| NCMC information | — | Info module | Static content with sources | Info screen | Official NPCI/bank pages | None for information | Content tests | Planned |
| NCMC card operations | — | — | — | — | Banks/NPCI | **Bank/NPCI integration + hardware** | — | Blocked (out of scope) |

## Commuter extras

| Feature | Existing | Missing | Backend | Frontend | Data source | Permission | Tests | Status |
|---|---|---|---|---|---|---|---|---|
| Airport bus finder | — | Filter Vayu Vajra-type routes | Tag routes (admin-curated) | Airport tile | GTFS + admin tags | Feed licence | New | Planned |
| Facilities (toilets, water, parking, accessibility, help centres) | — | Everything | Facilities table, import from OSM | Map layer | OSM (ODbL) | ODbL attribution | New | Planned |
| Emergency contacts | — | Static, sourced list | Content | Help screen | Official numbers (112 etc.) | None | Content tests | Planned |
| SOS | — | Workflow | Delivery adapter | SOS screen with `tel:112` fallback | SMS/WhatsApp provider | **Paid SMS/WhatsApp provider**; free path is phone dialler only | "No false success" tests | Partial possible (dialler + share location); delivery Blocked |
| Help & support | — | Pages, FAQ, contact | Content | Help screen | — | — | New | Planned |

## Accounts and personalisation

| Feature | Existing | Missing | Backend | Frontend | Data source | Permission | Tests | Status |
|---|---|---|---|---|---|---|---|---|
| Guest mode | Device key | — | — | — | — | — | Exist | Done |
| Register / login | — | Everything | Users, argon2id, sessions, CSRF | Screens | — | Persistent DB (D-DB) | Auth tests | Planned (needs D-DB) |
| Profile, preferences, language | Preferences per device | Account-level | Profile APIs | Screens | — | D-DB | New | Partial |
| Favourite stops, saved journeys, recent searches | Saved routes | Others | Tables + APIs | Screens | — | D-DB | New | Planned |
| Notifications | — | Settings + Web Push | VAPID push | Permission prompt | — | Free (Web Push) | New | Planned |
| Account deletion, data export | — | Everything | APIs | Screens | — | D-DB | New | Planned |
| OTP login by SMS | — | — | — | — | SMS provider | **Paid** | — | Blocked (not planned) |

## Languages

| Feature | Existing | Missing | Status |
|---|---|---|---|
| EN / KN / TE / HI UI text | 344 keys each, translation file | New 4.0 screens; native-speaker review | Partial |
| Review checklist | — | Checklist doc | Planned |

## AI travel assistant

| Feature | Existing | Missing | Backend | Data | Permission | Status |
|---|---|---|---|---|---|---|
| Rule-based assistant (free) | — | Intent parsing over own APIs; answers only from database with source + date | Retrieval layer | App DB | None | Planned |
| LLM assistant (optional) | — | Tool-calling over the same retrieval layer | Provider adapter | App DB | **Paid API key** (optional) | Planned, off by default |

## Admin

| Feature | Existing | Missing | Status |
|---|---|---|---|
| GTFS import, validation, source verification, audit log, backups, stats | Yes | Redesign | Done |
| Role-based admin accounts | Single key | Users with roles | Planned |
| Data freshness, provider health, feature flags, API usage, security events | — | All | Planned |

## Android and PWA

| Feature | Existing | Missing | Status |
|---|---|---|---|
| Launcher icon, launch screen | Yes | Animated splash in the web app | Partial |
| Back navigation, location permission, offline/error screen, deep links | — | All | Planned |
| Release signing | Debug key | Keystore in GitHub secrets (your action) | Blocked on your action |
| Emulator test | — | CI emulator smoke test | Planned |
| Real-device test | You installed it | Structured checklist | Partial (manual) |
| PWA install, offline, icons | Yes | Privacy policy, terms, SEO meta | Partial |
