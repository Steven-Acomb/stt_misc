"""FastAPI app: filesystem browse, transcription jobs, transcript review.

No auth by design — the tailnet is the security boundary. Browse spans the whole
disk (Steve's choice), but the media endpoint only ever serves audio-extension
files, and there are no write/delete-to-disk endpoints beyond saving transcript
edits back into the transcripts folder.
"""

from __future__ import annotations

import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path

import re

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import AUDIO_EXTENSIONS
from ..formatters import to_screenplay
from ..models import Transcript
from . import config
from .jobs import JobManager
from .log import log

TRANSCRIPT_EXTS = {".md", ".json"}

_AUDIO_MIMETYPES = {
    ".m4a": "audio/mp4", ".m4b": "audio/mp4", ".mp4": "audio/mp4",
    ".aac": "audio/aac", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".flac": "audio/flac", ".ogg": "audio/ogg", ".webm": "audio/webm",
}

jobs = JobManager()


class JobRequest(BaseModel):
    # Module-level (NOT nested in create_app): with `from __future__ import
    # annotations` the annotation is a string FastAPI resolves against module
    # globals — a nested class isn't there, and the body param silently becomes
    # a query param (422 "field required").
    path: str
    speakers: int | None = 2


class NoCacheStatic(StaticFiles):
    """Serve static assets with revalidation so JS/CSS edits aren't cached stale."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


def _kind(name: str) -> str | None:
    ext = Path(name).suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in TRANSCRIPT_EXTS:
        return "transcript"
    return None


def _resolve_transcript(transcript_id: str) -> Path:
    """Map a transcript id (relative posix path) to a .json under TRANSCRIPTS_DIR."""
    base = config.TRANSCRIPTS_DIR.resolve()
    p = (base / transcript_id).resolve()
    if base != p and base not in p.parents:
        raise HTTPException(400, "invalid transcript id")
    if p.suffix.lower() != ".json":
        p = p.with_suffix(".json")
    return p


def create_app() -> FastAPI:
    app = FastAPI(title="stt-misc web", docs_url=None, redoc_url=None)
    config.TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # ---- health -------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"ok": True}

    # ---- filesystem browse -------------------------------------------
    @app.get("/api/fs")
    def fs_browse(path: str | None = None):
        if path is None:
            if hasattr(os, "listdrives"):
                roots = os.listdrives()
            else:
                roots = ["/"]
            return {"path": None, "parent": None, "dirs": roots, "files": []}
        p = os.path.abspath(path)
        if not os.path.exists(p):
            raise HTTPException(404, f"no such path: {p}")
        if not os.path.isdir(p):
            raise HTTPException(400, f"not a directory: {p}")
        dirs: list[str] = []
        files: list[dict] = []
        try:
            with os.scandir(p) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    try:
                        if entry.is_dir():
                            dirs.append(entry.name)
                        elif entry.is_file():
                            kind = _kind(entry.name)
                            if kind:
                                files.append({"name": entry.name, "kind": kind})
                    except OSError:
                        continue
        except OSError as e:
            raise HTTPException(400, f"cannot list {p}: {e}")
        parent = os.path.dirname(p)
        return {
            "path": p,
            "parent": parent if parent != p else None,
            "dirs": sorted(dirs, key=str.casefold),
            "files": sorted(files, key=lambda f: f["name"].casefold()),
        }

    # ---- audio streaming (extension-guarded) -------------------------
    @app.get("/api/audio")
    def get_audio(path: str):
        p = Path(os.path.abspath(path))
        if p.suffix.lower() not in AUDIO_EXTENSIONS:
            raise HTTPException(403, "not an audio file")
        if not p.is_file():
            raise HTTPException(404, "audio file not found")
        mt = _AUDIO_MIMETYPES.get(p.suffix.lower()) or mimetypes.guess_type(str(p))[0] \
            or "application/octet-stream"
        return FileResponse(str(p), media_type=mt)  # Range handled by Starlette

    # ---- transcripts list --------------------------------------------
    @app.get("/api/transcripts")
    def list_transcripts():
        base = config.TRANSCRIPTS_DIR
        out = []
        for js in sorted(base.rglob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                data = json.loads(js.read_text(encoding="utf-8"))
            except Exception:
                continue
            if "segments" not in data:
                continue  # not a transcript json
            out.append({
                "id": js.relative_to(base).as_posix(),
                "name": js.stem,
                "audio_name": data.get("audio_filename", ""),
                "duration_ms": data.get("duration_ms", 0),
                "speaker_count": len(data.get("speaker_names", {})),
                "modified_at": data.get("modified_at", ""),
                "mtime": js.stat().st_mtime,
            })
        return out

    # ---- one transcript (load / save) --------------------------------
    @app.get("/api/transcript/{transcript_id:path}")
    def get_transcript(transcript_id: str):
        p = _resolve_transcript(transcript_id)
        if not p.is_file():
            raise HTTPException(404, "transcript not found")
        transcript = Transcript.load(p)
        audio = Path(transcript.audio_path)
        payload = transcript.to_dict()
        payload["id"] = transcript_id
        payload["audio_available"] = audio.is_file()
        payload["audio_path"] = transcript.audio_path
        return payload

    @app.put("/api/transcript/{transcript_id:path}")
    async def put_transcript(transcript_id: str, body: dict):
        p = _resolve_transcript(transcript_id)
        if not p.is_file():
            raise HTTPException(404, "transcript not found")
        if not isinstance(body, dict) or "segments" not in body:
            raise HTTPException(400, "invalid transcript payload")
        try:
            transcript = Transcript.from_dict(body)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"could not parse transcript: {exc}")
        transcript.modified_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        transcript.save(p)
        p.with_suffix(".md").write_text(to_screenplay(transcript), encoding="utf-8")
        return {"ok": True, "modified_at": transcript.modified_at}

    # ---- download a transcript (md or json) --------------------------
    @app.get("/api/download/{transcript_id:path}")
    def download_transcript(transcript_id: str, fmt: str = "md"):
        p = _resolve_transcript(transcript_id)  # the .json
        if fmt == "json":
            target, media = p, "application/json"
        else:
            target, media = p.with_suffix(".md"), "text/markdown; charset=utf-8"
        if not target.is_file():
            raise HTTPException(404, "file not found")
        # filename= sets Content-Disposition: attachment, so phones offer "save".
        return FileResponse(str(target), media_type=media, filename=target.name)

    # ---- upload from the phone ---------------------------------------
    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)):
        raw = os.path.basename(file.filename or "upload")
        ext = Path(raw).suffix.lower()
        if ext not in AUDIO_EXTENSIONS:
            raise HTTPException(400, f"not an audio file: {raw}")
        # Keep the name readable but strip anything path-ish or unsafe.
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(raw).stem).strip() or "upload"
        config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = config.UPLOAD_DIR / f"{stem}{ext}"
        n = 2
        while dest.exists():
            dest = config.UPLOAD_DIR / f"{stem} ({n}){ext}"
            n += 1
        size = 0
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                size += len(chunk)
        log(f"upload saved: {dest.name} ({size/1_000_000:.1f} MB)")
        return {"path": str(dest), "name": dest.name, "bytes": size}

    # ---- transcription jobs ------------------------------------------
    @app.post("/api/jobs")
    def create_job(req: JobRequest):
        p = Path(os.path.abspath(req.path))
        if p.suffix.lower() not in AUDIO_EXTENSIONS:
            raise HTTPException(400, "not an audio file")
        if not p.is_file():
            raise HTTPException(404, f"audio file not found: {p}")
        speakers = req.speakers if (req.speakers and req.speakers > 0) else None
        job = jobs.submit(str(p), speakers)
        return job.to_dict()

    @app.get("/api/jobs")
    def list_jobs():
        return jobs.list()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "unknown job")
        return job.to_dict()

    # ---- static PWA (mounted last so /api/* wins) --------------------
    if config.STATIC_DIR.is_dir():
        app.mount("/", NoCacheStatic(directory=str(config.STATIC_DIR), html=True), name="static")

    log(f"app created (transcripts={config.TRANSCRIPTS_DIR})")
    return app


app = create_app()
