"""Tiny append-only logger, opened per write.

Deliberately NOT a long-lived file handle: the scheduled task that keeps this
app online restarts it, and a held-open log handle is exactly what makes those
restarts die silently (see docs/DEPLOY_TAILNET.md). Open, write, close.
"""

from __future__ import annotations

from datetime import datetime

from . import config


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {message}\n"
    try:
        config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(config.LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        # Logging must never take the app down.
        pass
