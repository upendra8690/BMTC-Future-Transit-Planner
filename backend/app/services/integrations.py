"""Adapters for provider integrations that need an authorisation the app does not have.

Each capability (live vehicles, bus tickets, passes, Metro QR tickets, payments, NCMC) has one adapter. Today every
adapter is the NotAuthorised adapter: it refuses every request with a stable code and points to the official channel.
It never returns a ticket, QR code, receipt, balance, payment confirmation or vehicle position.

A real integration is added by writing a new adapter class for one provider and registering it in ADAPTERS only after
a written agreement and credentials exist. Credentials would come from environment variables, never from the code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class IntegrationUnavailableError(Exception):
    """The capability needs an authorised provider that is not connected."""

    def __init__(self, capability: str, code: str, official_url: str | None) -> None:
        super().__init__(f"{capability}: {code}")
        self.capability = capability
        self.code = code
        self.official_url = official_url


@dataclass(frozen=True)
class NotAuthorised:
    capability: str
    code: str
    needs: str
    official_url: str | None

    connected: bool = False

    def describe(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "connected": self.connected,
            "status": "AWAITING_PROVIDER_ACCESS",
            "code": self.code,
            "needs": self.needs,
            "official_url": self.official_url,
        }

    def request(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        raise IntegrationUnavailableError(self.capability, self.code, self.official_url)


BMTC = "https://mybmtc.karnataka.gov.in/"
BMRCL = "https://english.bmrc.co.in/"

ADAPTERS: dict[str, NotAuthorised] = {
    "live_vehicles": NotAuthorised("live_vehicles", "NO_AUTHORISED_LIVE_FEED",
                                   "A data-sharing agreement with BMTC for live vehicle positions", BMTC),
    "bus_tickets": NotAuthorised("bus_tickets", "NEEDS_TICKETING_AGREEMENT",
                                 "A ticketing agreement with BMTC", BMTC),
    "bus_passes": NotAuthorised("bus_passes", "NEEDS_TICKETING_AGREEMENT",
                                "A ticketing agreement with BMTC", BMTC),
    "metro_qr_tickets": NotAuthorised("metro_qr_tickets", "NEEDS_ONDC_REGISTRATION",
                                      "ONDC registration and BMRCL approval", BMRCL),
    "payments": NotAuthorised("payments", "NEEDS_PAYMENT_GATEWAY",
                              "A merchant agreement with a licensed payment aggregator", None),
    "ncmc": NotAuthorised("ncmc", "NEEDS_BANK_INTEGRATION",
                          "An issuing-bank and operator agreement for NCMC", None),
}


def adapter(capability: str) -> NotAuthorised:
    try:
        return ADAPTERS[capability]
    except KeyError:
        raise IntegrationUnavailableError(capability, "UNKNOWN_CAPABILITY", None) from None


def status() -> dict[str, Any]:
    return {
        "note": "No ticket, pass, QR code, payment, wallet balance or live position is ever produced by this app "
                "until an authorised provider is connected.",
        "integrations": [a.describe() for a in ADAPTERS.values()],
    }
