# 14 Implementation and maintenance costs

**No funding is requested from the authority.** The costs below would be borne by the applicant. Prices are
indicative only and must be confirmed on each vendor's pricing page at the time of budgeting. Prices quoted in US
dollars are charged in dollars.

## Today
| Item | Provider | Cost |
|---|---|---|
| Hosting for the 3.0 demo and the separate 4.0 service | Render free plan | ₹0 |
| Source code, automated tests, Android builds | GitHub free plan | ₹0 |
| Maps | OpenStreetMap tiles (light use) | ₹0 |
| Development | The applicant's own time | Not charged |
| **Total** | | **₹0 per month** |

## For a six-week pilot (indicative)
| Item | Why it is needed | Indicative cost |
|---|---|---|
| Always-on web service | No sleeping; stable for participants | Render's paid "Starter" instance, about US$7 a month at the time of writing |
| PostgreSQL with backups | Data survives restarts; daily backups | Free tier may be enough for 50 participants; otherwise the vendor's entry-level paid plan |
| Domain name (optional) | A clear address | About ₹1,000 a year |
| Uptime monitoring | Measures availability | A free tier is enough |
| Android distribution (optional) | Play Store instead of a direct download | Google Play developer registration, one-time US$25 |
| Legal review of the privacy policy | Before collecting any feedback | To be quoted |
| Native-speaker translation review | Kannada, Telugu, Hindi | Volunteer, or to be quoted |

## Maintenance after a pilot
| Activity | Frequency | Who |
|---|---|---|
| Import each new official feed and verify it | Whenever the publisher releases one | The applicant (Administration screen) |
| Dependency and security updates | Monthly, plus urgent fixes | The applicant; pip-audit and bandit run in checks |
| Automated tests | On every change | GitHub Actions |
| Backups and restore drill | Daily backups; a restore drill every quarter | The applicant (`scripts/backup_database.py`, `scripts/restore_drill.sh`) |
| Review of upcoming-transport statuses | Monthly, and when operators announce changes | The applicant |

## Cost to the authority
Only staff time:
- to review the application;
- to provide data and its licence;
- to nominate a contact for the pilot.

No payment, infrastructure or software purchase is requested.
