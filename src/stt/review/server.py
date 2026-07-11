"""Flask app serving the transcript editor.

Endpoints:
  GET  /                 -> the editor page
  GET  /api/transcript   -> current transcript JSON
  PUT  /api/transcript   -> save transcript JSON, regenerate the screenplay
  GET  /api/audio        -> stream the audio file (supports HTTP Range for seeking)
  GET  /static/<file>    -> app.js / style.css
"""

from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

from ..formatters import to_screenplay
from ..models import Transcript

STATIC_DIR = Path(__file__).parent / "static"

_AUDIO_MIMETYPES = {
    ".m4a": "audio/mp4",
    ".m4b": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
}


def resolve_audio_path(transcript: Transcript, json_path: Path, override: str | None) -> Path | None:
    """Find the audio file, trying the override, the stored path, and the JSON dir."""
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    stored = Path(transcript.audio_path)
    candidates.append(stored)
    if not stored.is_absolute():
        candidates.append((json_path.parent / stored).resolve())
    # Same folder as the JSON, matching the stored filename.
    candidates.append(json_path.parent / transcript.audio_filename)
    for c in candidates:
        if c and c.exists():
            return c.resolve()
    return None


def create_app(json_path: Path, screenplay_path: Path, audio_override: str | None = None) -> Flask:
    json_path = Path(json_path).resolve()
    screenplay_path = Path(screenplay_path).resolve()

    app = Flask(__name__, static_folder=None)

    def _load() -> Transcript:
        return Transcript.load(json_path)

    @app.get("/")
    def index() -> Response:
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str) -> Response:
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/api/transcript")
    def get_transcript():
        transcript = _load()
        audio = resolve_audio_path(transcript, json_path, audio_override)
        payload = transcript.to_dict()
        payload["audio_available"] = audio is not None
        payload["audio_resolved_path"] = str(audio) if audio else None
        return jsonify(payload)

    @app.put("/api/transcript")
    def put_transcript():
        data = request.get_json(force=True, silent=False)
        if not isinstance(data, dict) or "segments" not in data:
            return jsonify({"error": "invalid transcript payload"}), 400
        try:
            transcript = Transcript.from_dict(data)
        except Exception as exc:  # noqa: BLE001 - surface parse errors to the client
            return jsonify({"error": f"could not parse transcript: {exc}"}), 400

        # Bump modified time and persist both the JSON (source of truth) and the
        # regenerated screenplay so the .md the user ultimately keeps stays current.
        from datetime import datetime, timezone

        transcript.modified_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        transcript.save(json_path)
        screenplay_path.parent.mkdir(parents=True, exist_ok=True)
        screenplay_path.write_text(to_screenplay(transcript), encoding="utf-8")
        return jsonify({"ok": True, "modified_at": transcript.modified_at})

    @app.get("/api/audio")
    def get_audio():
        transcript = _load()
        audio = resolve_audio_path(transcript, json_path, audio_override)
        if audio is None:
            return jsonify({"error": "audio file not found"}), 404
        mimetype = _AUDIO_MIMETYPES.get(audio.suffix.lower())
        if mimetype is None:
            mimetype = mimetypes.guess_type(str(audio))[0] or "application/octet-stream"
        # conditional=True enables HTTP Range responses, which the browser's
        # <audio> element needs in order to seek.
        return send_file(str(audio), mimetype=mimetype, conditional=True)

    return app


def serve(
    json_path: Path,
    screenplay_path: Path,
    *,
    audio_override: str | None = None,
    host: str = "127.0.0.1",
    port: int = 5005,
    open_browser: bool = True,
) -> None:
    app = create_app(json_path, screenplay_path, audio_override)
    url = f"http://{host}:{port}/"

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    print(f"\n  Transcript editor running at {url}")
    print("  Press Ctrl+C to stop.\n")
    # threaded=True so audio streaming doesn't block API/save requests.
    app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)
