"""Unit tests for input-safety helpers: filenames, device-key handling and the rate limiter."""

from __future__ import annotations

from app.security import CLIENT_KEY_RE, RateLimiter, client_hash, safe_filename


def test_filenames_lose_their_directories_and_unsafe_characters():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("C:\\Users\\me\\feed one.zip") == "feed_one.zip"
    assert safe_filename(None) == "upload.zip"
    assert len(safe_filename("a" * 500 + ".zip")) <= 120


def test_device_keys_are_stored_only_as_sha256():
    digest = client_hash("client-a-0123456789abcdef")
    assert len(digest) == 64
    assert "client-a" not in digest
    assert client_hash("client-a-0123456789abcdef") == digest


def test_device_key_format_is_enforced():
    assert CLIENT_KEY_RE.fullmatch("client-a-0123456789abcdef")
    assert not CLIENT_KEY_RE.fullmatch("short")
    assert not CLIENT_KEY_RE.fullmatch("has spaces in it 0123456789")


def test_rate_limiter_counts_per_key_and_slides_forward():
    limiter = RateLimiter(per_minute=2, window_seconds=60)
    assert limiter.allow("a", now=0)
    assert limiter.allow("a", now=1)
    assert not limiter.allow("a", now=2)
    assert limiter.allow("b", now=2)
    assert limiter.allow("a", now=61.5)  # the first two hits have left the window
