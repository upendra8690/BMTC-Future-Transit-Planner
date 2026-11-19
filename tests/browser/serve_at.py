"""Run the server as if it were a chosen moment, so browser checks give the same answer at any hour. Test use only.

Usage (from the project folder, with the usual environment variables):
  python tests/browser/serve_at.py 2026-11-19T10:00+05:30 8030

The server's clock starts at that moment and then runs at normal speed. Journey planning, departures and the clock bar
all read the time through app.clock.utc_now, which is the only thing replaced. Nothing here is used in production.
"""

from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import uvicorn
from app import clock

start = dt.datetime.fromisoformat(sys.argv[1]).astimezone(dt.UTC)
port = int(sys.argv[2])
began = time.monotonic()
clock.utc_now = lambda: start + dt.timedelta(seconds=time.monotonic() - began)

uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=port, log_level="warning")
