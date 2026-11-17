# Privacy and accessibility — 4.0.0-beta.1

## Privacy (what the software actually does)
| Data | Kept where | How long |
|---|---|---|
| Random device key | Browser; the server keeps only its SHA-256 hash | Until "Delete my data" or the browser is cleared |
| Saved routes, scenarios, preferences | Server, under the hash | Until deleted, or "Delete my data" |
| Favourite stops, recent searches, language, theme, low-data and large-text settings | Browser only | Until cleared |
| Searches, journey requests, assistant questions | Not stored by the app (no access log; the app logs path without query) | — |
| Location | Sent only with a "Stops near me" request; not stored | — |
| Name, phone, email, payment details | Never collected | — |

- No analytics, advertising, crash reporting or AI services.
- The service worker never keeps a copy of a typed search, so a search for a place is not stored on the device.
- Third parties: the hosting provider (Render) sees every request and IP address. OpenStreetMap tile servers see the
  IP address and the map area.
- Drafts of the privacy policy, terms and retention policy are in `docs/government/`. They have not been reviewed by
  a lawyer.

## Accessibility
| Check | Result |
|---|---|
| axe-core scan, WCAG 2.0/2.1 A and AA plus best practice, phone size | **No violations** on 15 screens and states × light and dark themes (`tests/audit/audit_a11y.py`) |
| Screens scanned | Home, Nearby, Plan, Live, Tickets, Metro, Favourites, My account, More, Upcoming transport, Travel assistant, Data and providers, a stop page, a journey result, an assistant answer |
| Keyboard | Every control is a native button, link or form field; tables are focusable labelled regions; Escape closes menus and dialogs (browser checks) |
| Text size | Large-text setting; layout holds at 390 px with no horizontal scroll in all four languages |
| Colour | Dark and light themes scanned separately for contrast |
| Live regions | Journey results and assistant answers are announced (`aria-live="polite"`) |
| Not done | A test with a real screen reader (TalkBack or NVDA) or with disabled users. Automated scans find only some problems |

## Languages
English, Kannada, Telugu and Hindi. A test enforces that every language has exactly the same keys and that every
message code the server can send is translated. **The translations have not been professionally reviewed.** Travel
assistant questions are understood in English only. Upcoming-project descriptions and provider details come from
the server in English.
