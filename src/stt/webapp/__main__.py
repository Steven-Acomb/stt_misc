"""Run the web app: `python -m stt.webapp` (bound to 127.0.0.1:8792 by default).

Exposed to the phone over Tailscale; see docs/DEPLOY_TAILNET.md.
"""

from __future__ import annotations

import sys

import uvicorn

from . import config
from .log import log


def _ensure_streams() -> None:
    """pythonw.exe (used by the SttWebApp scheduled task) runs with no console,
    so sys.stdout/sys.stderr are None — which makes uvicorn's logging setup crash
    on startup. Point them at a file so the app runs headless under the task."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stream = open(
        config.LOG_FILE.with_name("webapp.out.log"),
        "a", buffering=1, encoding="utf-8", errors="replace",
    )
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def main() -> None:
    _ensure_streams()
    log(f"starting uvicorn on {config.HOST}:{config.PORT}")
    uvicorn.run(
        "stt.webapp.app:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
