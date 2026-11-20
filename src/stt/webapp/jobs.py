"""Async transcription jobs.

A phone request to transcribe returns immediately with a job id; the actual
AssemblyAI call (minutes long) runs on a background thread pool. The phone polls
the job list for status. Completed transcripts are written to disk exactly like
the CLI. The job list itself is mirrored to config.JOBS_FILE after every change,
and on startup any job that was queued or running is re-submitted, so a reboot
or task restart mid-transcription costs a retry, not the job.
"""

from __future__ import annotations

import json
import os
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


KEEP_HISTORY = 200  # finished jobs retained in the list / on disk


class Job:
    def __init__(self, audio_path: str, speakers: int | None, unreviewed: bool = False):
        self.id = uuid.uuid4().hex[:12]
        self.audio_path = audio_path
        self.audio_name = Path(audio_path).name
        self.speakers = speakers
        self.unreviewed = unreviewed
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
            "unreviewed": self.unreviewed,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "transcript_id": self.transcript_id,
            "duration_ms": self.duration_ms,
            "speaker_count": self.speaker_count,
            "resumed": getattr(self, "resumed", 0),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        job = cls(d.get("audio_path", ""), d.get("speakers"), bool(d.get("unreviewed", False)))
        job.id = d.get("id") or job.id
        job.audio_name = d.get("audio_name") or job.audio_name
        job.status = d.get("status", "queued")
        job.error = d.get("error", "")
        job.created_at = d.get("created_at") or job.created_at
        job.started_at = d.get("started_at")
        job.finished_at = d.get("finished_at")
        job.transcript_id = d.get("transcript_id")
        job.duration_ms = d.get("duration_ms", 0) or 0
        job.speaker_count = d.get("speaker_count", 0) or 0
        job.resumed = int(d.get("resumed", 0) or 0)
        return job


class JobManager:
    def __init__(self, max_workers: int | None = None, state_file=None):
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()  # serialises the write+replace below
        self._state_file = state_file or config.JOBS_FILE
        self._pool = ThreadPoolExecutor(max_workers=max_workers or config.MAX_WORKERS)
        self._restore()

    # ---- persistence ----
    def _save(self) -> None:
        """Mirror the job list to disk (atomic replace). Never raises."""
        try:
            with self._save_lock:
                with self._lock:
                    ids = self._order[-KEEP_HISTORY:]
                    payload = [self._jobs[i].to_dict() for i in ids]
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._state_file.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
                os.replace(tmp, self._state_file)
        except Exception as exc:  # noqa: BLE001 - persistence must never break serving
            log(f"jobs: could not save state: {exc}")

    def _restore(self) -> None:
        """Load the saved list; re-queue anything that was unfinished."""
        if not self._state_file.is_file():
            return
        try:
            saved = json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log(f"jobs: could not read state file: {exc}")
            return
        resumed = 0
        for d in saved:
            try:
                job = Job.from_dict(d)
            except Exception:
                continue
            self._jobs[job.id] = job
            self._order.append(job.id)
            if job.status in ("queued", "running"):
                if not os.path.isfile(job.audio_path):
                    job.status = "error"
                    job.error = "audio file missing when the server restarted"
                    job.finished_at = time.time()
                    continue
                job.status = "queued"
                job.started_at = None
                job.resumed += 1
                resumed += 1
                self._pool.submit(self._run, job.id)
        log(f"jobs: restored {len(self._order)} from {self._state_file.name}, re-queued {resumed}")
        if resumed:
            self._save()

    def submit(self, audio_path: str, speakers: int | None, unreviewed: bool = False) -> Job:
        job = Job(audio_path, speakers, unreviewed)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        log(f"job {job.id} queued: {job.audio_name} (speakers={speakers}, unreviewed={unreviewed})")
        self._save()
        self._pool.submit(self._run, job.id)
        return job

    def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        job.status = "running"
        job.started_at = time.time()
        log(f"job {job.id} running: {job.audio_name}")
        self._save()
        try:
            transcript = transcribe_file(
                job.audio_path, speakers_expected=job.speakers
            )
            stem = _slug(job.audio_name) + (config.UNREVIEWED_SUFFIX if job.unreviewed else "")
            md, js = _unique_output(stem)
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
            self._save()

    def list(self) -> list[dict]:
        with self._lock:
            return [self._jobs[i].to_dict() for i in reversed(self._order)]

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)
