# 14 Implementation budget and maintenance costs

**No funding is requested from the authority.** The applicant would bear the costs below.
- Prices are indicative. Confirm each one on the vendor's pricing page before budgeting.
- Dollar prices are charged in dollars, so the rupee cost depends on the exchange rate.
- Items marked "to be quoted" have no estimate here, because none could be verified.

## Option 0: zero-budget demonstration (today)
| Item | Provider | Cost |
|---|---|---|
| Public preview and the separate 3.0 demonstration | Render free plan | ₹0 |
| Source code, automated tests, Android test builds | GitHub free plan (public repository) | ₹0 |
| Maps | OpenStreetMap tiles (light use, under its usage policy) | ₹0 |
| Installable app on any phone | Progressive web app (no store needed) | ₹0 |
| Android testing | Android emulator on the developer's computer | ₹0 |
| Development and support | The applicant's own time | Not charged |
| **Total** | | **₹0 a month** |

**Limits of Option 0:**
- The server sleeps when idle, so the first visit can take up to a minute.
- Saved data on the server is lost on restart.
- There is no service-level guarantee.
- It is suitable for review and demonstration, **not** for a pilot.

## Option 1: minimum pilot
| Item | Why | Indicative cost |
|---|---|---|
| Always-on web service | No sleeping during the pilot | Render "Starter", about US$7 a month |
| PostgreSQL with backups | Data survives restarts; daily backups | Render Postgres entry plan, about US$6 a month |
| Domain name | A clear, stable address | About ₹1,000 a year |
| Uptime monitoring | Measures availability | Free tier |
| **Total** | | **About US$13 a month, plus the domain** |

## Option 2: pilot with assurance (recommended if the authority asks for it)
Everything in Option 1, plus:

| Item | Why | Indicative cost |
|---|---|---|
| Security audit and "safe to host" clearance by a CERT-In-empanelled auditor or STQC | GIGW 3.0, if the authority requires it | To be quoted (ask at least three empanelled auditors) |
| Hosting in India (for example a MeitY-empanelled cloud) | If the authority requires data to stay in India | To be quoted |
| Legal review of the privacy notice (DPDP Act, 2023) | Before any feedback is collected | To be quoted |
| Accessibility review with screen-reader users | Beyond automated scans | Volunteers, or to be quoted |
| Native-speaker review of Kannada, Telugu and Hindi | Translation quality | Volunteers, or to be quoted |
| Map tiles from a commercial provider | If use exceeds OpenStreetMap's light-use policy | Free tiers exist; to be quoted above them |
| Google Play developer registration | Only if a Play Store app is in scope | One-time US$25 |
| Apple Developer Program | Only if an iPhone App Store app is in scope (needs a Mac to build) | US$99 a year |

## Option 3: an official production service
**Not estimated.** A service run for or by an authority needs that authority's written requirements, so it cannot
be costed honestly before they exist. Those requirements include:
- user numbers and availability targets;
- hosting and security rules;
- support hours;
- live data, ticketing and payment agreements.

## Maintenance
| Activity | Frequency | Who |
|---|---|---|
| Import each new official feed and verify it | Whenever the publisher releases one | Applicant (Administration screen) |
| Dependency and security updates | Monthly, plus urgent fixes | Applicant; pip-audit and bandit |
| Automated tests | On every change | GitHub Actions |
| Backups and restore drill | Daily backups; a drill every quarter | Applicant |
| Review of upcoming-transport statuses | Monthly, and when operators announce changes | Applicant |

## Cost to the authority
Only staff time:
- to review the application;
- to provide data and its licence;
- to nominate a contact officer;
- to decide on the pilot.

No payment, infrastructure or software purchase is requested.
