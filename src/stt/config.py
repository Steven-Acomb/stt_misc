"""Configuration and small shared helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load a .env from the project root / current dir if present. Never fatal.
load_dotenv()

API_KEY_ENV = "ASSEMBLYAI_API_KEY"

# Audio extensions we recognize for batch discovery. AssemblyAI accepts far more;
# this list just controls what `stt batch` globs for.
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".mp4", ".webm", ".m4b"}

# Approximate USD/hour for cost estimates. AssemblyAI bills per second; these are
# rough figures for the "best" (Universal) model plus speaker diarization, used
# only to print an estimate before a batch run. Update if AssemblyAI's rates move.
COST_PER_HOUR_USD = 0.17  # ~0.15 base + ~0.02 diarization


def get_api_key() -> str:
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise SystemExit(
            f"Missing {API_KEY_ENV}. Set it in your environment or a .env file.\n"
            f"See HUMAN_TODO.md for setup instructions."
        )
    return key


def sidecar_json_path(output_path: str | Path) -> Path:
    """Given a screenplay output path (e.g. foo.md), return the JSON sidecar path.

    foo.md  -> foo.json
    foo     -> foo.json
    foo.txt -> foo.json
    """
    p = Path(output_path)
    return p.with_suffix(".json")
