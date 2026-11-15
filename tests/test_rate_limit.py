"""The per-client rate limiter: budgets, windows, and a bounded table that never resets everyone's budget at once."""

from __future__ import annotations

from app.security import RateLimiter


def test_each_client_gets_its_own_budget():
    limiter = RateLimiter(2, window_seconds=60)
    assert limiter.allow("203.0.113.1", now=0)
    assert limiter.allow("203.0.113.1", now=1)
    assert not limiter.allow("203.0.113.1", now=2)
    assert limiter.allow("203.0.113.2", now=2)


def test_the_budget_returns_as_old_hits_leave_the_window():
    limiter = RateLimiter(1, window_seconds=60)
    assert limiter.allow("a", now=0)
    assert not limiter.allow("a", now=59)
    assert limiter.allow("a", now=60.5)


def test_refusing_new_clients_does_not_reset_active_budgets():
    """A flood of new addresses must not clear the counts of clients that are already active."""
    limiter = RateLimiter(1, window_seconds=60, max_clients=2)
    assert limiter.allow("a", now=0)
    assert limiter.allow("b", now=0)
    assert not limiter.allow("c", now=1)  # the table is full of active clients, so a new one is refused
    assert not limiter.allow("a", now=2)  # a's budget is still spent, not reset


def test_idle_clients_are_forgotten_so_the_table_stays_bounded():
    limiter = RateLimiter(1, window_seconds=60, max_clients=2)
    assert limiter.allow("a", now=0)
    assert limiter.allow("b", now=0)
    assert limiter.allow("c", now=61)  # a and b have been idle for over a minute, so there is room
    assert len(limiter._hits) == 1
