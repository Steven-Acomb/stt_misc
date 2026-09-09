"""Web app configuration (paths, host/port). All env-overridable."""

from __future__ import annotations

import os
from pathlib import Path

# src/stt/webapp/config.py -> parents: [0]=webapp [1]=stt [2]=src [3]=repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# Where transcripts kicked off from the web app are written (and where the
# "existing transcripts" list is read from). Mirrors the CLI default.
TRANSCRIPTS_DIR = Path(os.environ.get("STT_TRANSCRIPTS_DIR", str(REPO_ROOT / "transcripts")))

# Where audio uploaded from the phone lands.
UPLOAD_DIR = Path(os.environ.get("STT_UPLOAD_DIR", str(REPO_ROOT / "uploads")))

# The app writes its own log, opened per-write (never a shell redirect) — this
# is what lets the scheduled task restart cleanly. See docs/DEPLOY_TAILNET.md.
LOG_FILE = Path(os.environ.get("STT_WEB_LOG", str(REPO_ROOT / "logs" / "webapp.log")))

HOST = os.environ.get("STT_WEB_HOST", "127.0.0.1")
PORT = int(os.environ.get("STT_WEB_PORT", "8792"))

STATIC_DIR = Path(__file__).parent / "static"

# How many transcription jobs run at once.
MAX_WORKERS = int(os.environ.get("STT_WEB_WORKERS", "2"))
