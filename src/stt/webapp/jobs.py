"""Async transcription jobs.

A phone request to transcribe returns immediately with a job id; the actual
AssemblyAI call (minutes long) runs on a background thread pool. The phone polls
the job list for status. Completed transcripts are written to disk exactly like
the CLI, so they persist even though the in-memory job list does not survive a
restart.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..formatters import to_screenplay
from ..transcribe import transcribe_file
from . import config
from .log import log

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(name: str) -> str:
    stem = Path(name).stem
    stem = _SAFE.sub("-", stem).strip("-")
    return stem or "transcript"


def _unique_output(stem: str) -> tuple[Path, Path]:
    """Return (md, json) under TRANSCRIPTS_DIR, not clobbering an existing pair."""
    base = config.TRANSCRIPTS_DIR
    md = base / f"{stem}.md"
    n = 2
    while md.exists() or md.with_suffix(".json").exists():
        md = base / f"{stem} ({n}).md"
        n += 1
    return md, md.with_suffix(".json")


class Job:
    def __init__(self, audio_path: str, speakers: int | None):
        self.id = uuid.uuid4().hex[:12]
        self.audio_path = audio_path
        self.audio_name = Path(audio_path).name
        self.speakers = speakers
        self.status = "queued"  # queued | running | done | error
        self.error = ""
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.output_md: str | None = None
        self.output_json: str | None = None
        self.transcript_id: str | None = None  # relative json path, for the editor
        self.duration_ms = 0
        self.speaker_count = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "audio_name": self.audio_name,
            "audio_path": self.audio_path,
            "speakers": self.speakers,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "transcript_id": self.transcript_id,
            "duration_ms": self.duration_ms,
            "speaker_count": self.speaker_count,
        }


class JobManager:
    def __init__(self, max_workers: int | None = None):
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers or config.MAX_WORKERS)

    def submit(self, audio_path: str, speakers: int | None) -> Job:
        job = Job(audio_path, speakers)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        log(f"job {job.id} queued: {job.audio_name} (speakers={speakers})")
        self._pool.submit(self._run, job.id)
        return job

    def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        job.status = "running"
        job.started_at = time.time()
        log(f"job {job.id} running: {job.audio_name}")
        try:
            transcript = transcribe_file(
                job.audio_path, speakers_expected=job.speakers
            )
            md, js = _unique_output(_slug(job.audio_name))
            transcript.save(js)
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_text(to_screenplay(transcript), encoding="utf-8")
            job.output_md = str(md)
            job.output_json = str(js)
            job.duration_ms = transcript.duration_ms
            job.speaker_count = len(transcript.speaker_names)
            try:
                job.transcript_id = js.relative_to(config.TRANSCRIPTS_DIR).as_posix()
            except ValueError:
                job.transcript_id = js.name
            job.status = "done"
            log(f"job {job.id} done: {md.name} "
                f"({job.duration_ms/60000:.1f} min, {job.speaker_count} spk)")
        except Exception as exc:  # noqa: BLE001 - record on the job, keep serving
            job.status = "error"
            job.error = str(exc)
            log(f"job {job.id} ERROR: {exc}")
        finally:
            job.finished_at = time.time()

    def list(self) -> list[dict]:
        with self._lock:
            return [self._jobs[i].to_dict() for i in reversed(self._order)]

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)
