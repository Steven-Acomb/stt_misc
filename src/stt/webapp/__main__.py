"""Run the web app: `python -m stt.webapp` (bound to 127.0.0.1:8792 by default).

Exposed to the phone over Tailscale; see docs/DEPLOY_TAILNET.md.
"""

from __future__ import annotations

import uvicorn

from . import config
from .log import log


def main() -> None:
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
