# 08 Accessibility and language support

## Accessibility: what was tested
| Check | Result | Method |
|---|---|---|
| WCAG 2.1 A and AA, plus best-practice rules | **No violations** on 15 screens and states, in light and dark themes | axe-core in Microsoft Edge (`tests/audit/audit_a11y.py`) |
| Small screens | All 18 screens fit 390 pixels with no sideways scrolling | e2e crawl at 390 × 844 |
| Every control has an accessible name | PASS | e2e labels check |
| Keyboard and focus | Covered by the axe rules and the browser regression checks | — |
| Large text, dark mode, low-data mode | Each switch changes the display | e2e |
| Location refusal | Clear message, and search by name still works | e2e |

## Accessibility: not yet tested
- **Real screen readers.** TalkBack on Android and NVDA on Windows. Planned before any pilot, with the pilot asking
  for at least three participants who use screen readers.
- **Guidelines for Indian Government Websites (GIGW 3.0).** Not assessed, because this is not a government website. We
  will follow the authority's guidance if a pilot proceeds.
- **Accessibility of stops and stations** (step-free access, lifts). Not shown, because no dataset is available.

Automated scans find only part of all accessibility problems. A manual review with disabled users is still needed.

## Languages
| Language | Interface | Review |
|---|---|---|
| English | Complete | — |
| ಕನ್ನಡ Kannada | Complete | Not yet reviewed by a native speaker |
| తెలుగు Telugu | Complete | Not yet reviewed by a native speaker |
| हिन्दी Hindi | Complete | Not yet reviewed by a native speaker |

- **Complete coverage.** A test fails if any interface text is missing in any of the four languages, or if text is
  built in a way that cannot be translated.
- **Behaviour.** The choice of language is remembered on the device. It sets the page language, so screen readers
  pronounce the text correctly, and it was verified after a refresh.
- **Not translated.** Stop and route names come from the operator's data and appear as published. Names in Kannada
  script will show in Kannada once official data provides them. The travel assistant understands English questions
  only.
- **Before a pilot.** We will ask native speakers to review all three translations. We would welcome the authority's
  preferred terms for transport words, such as stop, depot, interchange and feeder.
