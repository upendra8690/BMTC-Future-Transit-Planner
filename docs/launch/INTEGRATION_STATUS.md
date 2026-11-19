# Integration status

Source: `backend/app/services/integrations.py`. Live copy: `GET /api/integrations`.

Every capability that needs a provider goes through one adapter. Today each adapter is `NotAuthorised`. It refuses
every request with HTTP 503 and a stable code, and names the official channel. It never returns a ticket, QR code,
receipt, wallet balance, payment confirmation or vehicle position.

| Capability | Endpoint | Response today | Needs |
|---|---|---|---|
| Live vehicles / ETA | `POST /api/integrations/live_vehicles/request` | 503 `NO_AUTHORISED_LIVE_FEED` | Data-sharing agreement with BMTC |
| Bus tickets | `POST /api/integrations/bus_tickets/request` | 503 `NEEDS_TICKETING_AGREEMENT` | Ticketing agreement with BMTC |
| Bus passes | `POST /api/integrations/bus_passes/request` | 503 `NEEDS_TICKETING_AGREEMENT` | Ticketing agreement with BMTC |
| Metro QR tickets | `POST /api/integrations/metro_qr_tickets/request` | 503 `NEEDS_ONDC_REGISTRATION` | ONDC registration and BMRCL approval |
| Payments (UPI, cards, wallet) | `POST /api/integrations/payments/request` | 503 `NEEDS_PAYMENT_GATEWAY` | Merchant agreement with a licensed aggregator |
| NCMC | `POST /api/integrations/ncmc/request` | 503 `NEEDS_BANK_INTEGRATION` | Issuing-bank and operator agreement |
| Anything else | `POST /api/integrations/<other>/request` | 404 `UNKNOWN_CAPABILITY` | — |

Tested in `tests/test_launch.py`: each capability is refused with its code, and the response contains no ticket, QR,
receipt, balance, payment or transaction field. A malformed capability name returns 422.

## Adding a real integration (only after a written agreement)
1. Write a new adapter class for that provider, with the same `describe()` and `request()` methods.
2. Read credentials from environment variables set in the hosting dashboard. Never put them in Git.
3. Register the adapter in `ADAPTERS` and change the feature state in `catalogue.py`.
4. Add tests against the provider's sandbox, and record the agreement in the provider registry.

## Data feeds
| Feed | Status |
|---|---|
| Static GTFS import (any publisher) | Working: admin upload, validation, classification, verification |
| GTFS-Realtime (vehicle positions, trip updates, alerts) | Not connected; no authorised feed |
| DULT Transport Data Hub | Not connected; permission not yet requested |
