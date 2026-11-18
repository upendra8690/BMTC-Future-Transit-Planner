# 07 Privacy and data protection

The application is designed to collect as little personal data as possible.
- **No legal review has been done** against the Digital Personal Data Protection Act, 2023 and the DPDP Rules, 2025.
  One is planned before any pilot.
- The Rules were notified in November 2025, and most data-fiduciary obligations apply from May 2027.
- The draft privacy policy, terms and retention policy are in `docs/government/`.
- A checklist is in [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md), section 5.

**Passenger accounts** are built but switched off. If they are enabled, they hold a username or email, a password hash
and the journeys the passenger saves. Export and deletion are built in.

## What is collected
| Data | Where | Why | Kept for |
|---|---|---|---|
| A random device key | The device; the server keeps only its SHA-256 hash | To keep one device's saved items separate from another's | Until "Delete my data" |
| Saved routes and scenarios | Server, under the hashed key | The passenger chose to save them | Until the passenger removes them or erases their data |
| Saved stops and journeys, language and display settings | The device only | The passenger chose them | Until removed or the browser storage is cleared |
| Location | Not stored. Used once, in the browser, when the passenger taps "Stops near me" | To find nearby stops | Not kept |
| Searches and journeys planned | Not stored; there is no access log | — | — |

**Not collected:** names, phone numbers, email addresses, payment details, card numbers, UPI identifiers, contacts,
photos, advertising identifiers, or analytics of any kind.

## Passenger rights
- **Erasure.** "Delete my data" on the My account screen removes the server records, clears the device lists and
  creates a new device key. This was verified end to end in a real browser.
- **Access.** Everything kept about a device is shown on its own screens, so there is nothing hidden to request.
- **Consent.** Location is requested only when the passenger taps the button. A refusal is respected and gets a clear
  message.

## Third parties
| Party | What it sees | Note |
|---|---|---|
| Hosting provider (Render, Singapore region) | Network requests to the server | Required to serve the app; for a pilot, a host in India can be chosen if the authority prefers |
| OpenStreetMap tile servers | The passenger's IP address when map images load | Standard for any map; low-data mode reduces map use |
| GitHub | Nothing about passengers | Hosts the source code and the Android download |

## Security measures that protect personal data
Hashed device keys, strict input validation, a content security policy, rate limiting, HSTS, and secrets kept only in
the hosting environment. See [06](06_TECHNICAL_AND_SECURITY_REPORT.md).

## Before a pilot
1. A legal review of the privacy policy against the DPDP Act, 2023 and its Rules.
2. A named contact for privacy requests and grievances.
3. A retention period agreed with the authority, and deletion of all pilot data at the end on request.
4. Optional participant feedback collected with explicit consent and without names, unless the authority requires
   otherwise.
