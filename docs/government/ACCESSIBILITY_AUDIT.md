# Accessibility audit

Standard: WCAG 2.1 Level A and AA (the basis of GIGW 3.0, India's guidelines for government websites and apps), plus
axe-core best-practice rules. Tool: axe-core 4.14.0 in Microsoft Edge, phone size (390 × 844), light and dark themes.
Date: 16 November 2026.

## Screens scanned
Home, Nearby stops, Plan a journey, Live tracking, Tickets and passes, Namma Metro, Favourites, My account,
More services, and a stop page (departures table). The 3.0 screens are scanned by the existing browser checks.

## Results
| Run | Violations |
|---|---|
| First scan | 1 serious: `scrollable-region-focusable` — the departures table scrolled sideways but could not be reached by keyboard (light and dark) |
| After fix | **None** on all 10 screens in both themes |

Fix: every scrollable table is a focusable, labelled region (8 tables). A static test now enforces it.

The first version of the fix gave all tables the same label. The existing browser checks then reported `landmark-unique` (moderate) on the route page, which has several tables. Each table now has its own label (for example "Timetable", "Departures", or the direction heading). Retest: browser checks 121/121 and the 4.0 scan clean on all 10 screens in both themes.

## Other accessibility features
Larger-text setting; light/dark/device theme; 44 px minimum touch targets; skip link; keyboard-only operation tested
in the 3.0 browser checks; location requested only on tap; text in four languages with Indic font rules.

## Limits
Automated scans find only part of WCAG issues. Not yet done: screen-reader testing (TalkBack, NVDA), testing with
users with disabilities, and native-speaker review of the Kannada, Telugu and Hindi text.
