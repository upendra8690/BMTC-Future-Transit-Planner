"""Travel assistant: turns a typed question into one request to the app's own data.

This is a rule-based interpreter, not a language model. It never writes an answer itself. It recognises what the
traveller is asking for and returns an intent with parameters; the app then calls the matching endpoint (journey
planner, route search, stop search, Metro stations) and shows that endpoint's result with its source and date.

Questions about live arrivals, tickets, passes, payments and NCMC get a fixed reply saying the feature needs an
authorised provider, with the official channel. Emergencies get 112. English questions only, for now.
"""

from __future__ import annotations

import re
from typing import Any

MAX_QUESTION = 200

_EMERGENCY = re.compile(r"\b(emergency|accident|sos|ambulance|police|fire|unsafe|harass\w*|help me)\b")
_TICKETS = re.compile(r"\b(tickets?|pass|passes|qr|pay|payment|upi|wallet|ncmc|recharge|smart ?card|refund)\b")
_LIVE = re.compile(r"\b(live|eta|track\w*|arriv\w*|delay\w*|late|gps|where is (my|the) bus|when will)\b")
_JOURNEY = re.compile(r"^(?:.*?\bfrom\s+)?(?P<origin>.+?)\s+(?:to|till|until)\s+(?P<destination>.+)$")
_ROUTE = re.compile(r"\b(?:route|bus)\s*(?:no\.?|number|num)?\s*(?P<route>[0-9]{1,4}[a-z]{0,3}(?:-[0-9a-z]{1,4})?)\b")
_BARE_ROUTE = re.compile(r"^(?P<route>(?:[a-z]{1,3}-?)?[0-9]{1,4}[a-z]{0,3}(?:-[0-9a-z]{1,4})?)$")
_NEARBY = re.compile(r"\b(near me|nearby|nearest|close to me|around me)\b")
_METRO = re.compile(r"\b(metro|station|stations)\b")
_STOP = re.compile(r"\b(?:bus )?stop\s+(?:at|near|called|named)?\s*(?P<stop>.+)$")
_BY_METRO = re.compile(r"\b(by|only|using|via) metro\b|\bmetro only\b")
_BY_BUS = re.compile(r"\b(by|only|using|via) bus(es)?\b|\bbus(es)? only\b")
_LEADING = re.compile(r"^(how (do|can) i|how to|i want to|i need to|please|plan|show me|find|get|go|travel|reach)\s+")
_TRAILING = re.compile(r"[?.!]+$|\s+(today|now|tomorrow|please)$")
_STRIP_MODE = re.compile(r"\s*\b(?:by|only|using|via) (?:metro|bus(?:es)?)\b|\s*\b(?:metro|bus(?:es)?) only\b")

_NOT_PLACES = {"route", "bus", "a bus", "the bus", "metro", "way", "directions", "the way", "how"}


def _clean(text: str) -> str:
    text = text.strip()
    for _ in range(3):
        text = _LEADING.sub("", text)
        text = _TRAILING.sub("", text).strip()
    return text


def interpret(question: str) -> dict[str, Any]:
    """The intent of one question, with the parameters for the endpoint that answers it."""
    text = " ".join(question.lower().split())[:MAX_QUESTION]
    if not text:
        return {"intent": "help", "params": {}}
    if _EMERGENCY.search(text):
        return {"intent": "emergency", "params": {"tel": "112"}}
    if _TICKETS.search(text):
        return {"intent": "tickets", "params": {"feature": "bus_tickets"}}
    if _LIVE.search(text):
        return {"intent": "live", "params": {"feature": "live_tracking"}}

    modes = "metro" if _BY_METRO.search(text) else "bus" if _BY_BUS.search(text) else "all"
    match = _JOURNEY.match(_clean(_STRIP_MODE.sub("", text)))
    if match:
        origin = _clean(match.group("origin"))
        destination = _clean(match.group("destination"))
        if len(origin) >= 2 and len(destination) >= 2 and origin != destination and origin not in _NOT_PLACES:
            return {"intent": "journey", "params": {"origin": origin, "destination": destination, "modes": modes}}

    route = _ROUTE.search(text) or _BARE_ROUTE.match(_clean(text))
    if route:
        return {"intent": "route", "params": {"q": route.group("route").upper()}}
    if _NEARBY.search(text):
        return {"intent": "nearby", "params": {}}
    stop = _STOP.search(text)
    if stop and len(_clean(stop.group("stop"))) >= 2:
        return {"intent": "stop", "params": {"q": _clean(stop.group("stop"))}}
    if _METRO.search(text):
        name = _clean(_METRO.sub("", text)).strip()
        return {"intent": "metro", "params": {"q": name if len(name) >= 2 else ""}}
    cleaned = _clean(text)
    if 2 <= len(cleaned) <= 80:
        return {"intent": "stop", "params": {"q": cleaned}}
    return {"intent": "help", "params": {}}
