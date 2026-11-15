"""Text rules for names from any feed or user: one Unicode form, and a case-insensitive key for search.

Kannada, Devanagari and accented Latin text can be stored as composed or decomposed characters that look identical
on screen. Names are normalised to NFC when they are imported and when they are searched, so a search typed on any
keyboard finds the same stop. Case folding follows Unicode rules, so accented capitals match their lower-case forms.
"""

from __future__ import annotations

import unicodedata

# The SQL function registered on every SQLite connection (see app.database). It applies fold() inside the database.
FOLD_FUNCTION = "bmtc_fold"


def normalise(text: str) -> str:
    """Composed (NFC) characters, single spaces between words, no leading or trailing space."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def fold(text: str | None) -> str:
    """The search key for a piece of text: normalised and case-folded."""
    if text is None:
        return ""
    return normalise(text).casefold()
