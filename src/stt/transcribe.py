"""AssemblyAI transcription: audio file -> Transcript (with speaker diarization)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import assemblyai as aai

from .config import get_api_key
from .models import Segment, Transcript, Word


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# AssemblyAI's recommended model preference list (tried in order). The singular
# `speech_model` parameter is deprecated; `speech_models` takes a fallback list.
DEFAULT_MODELS = "universal-3-5-pro,universal-2"


def _parse_models(model: str) -> list[str]:
    return [m.strip() for m in model.split(",") if m.strip()]


# Container formats where the file is far bigger than its speech track: iOS 17+
# Voice Memos .qta holds AAC plus an Apple spatial-audio track (~4.5x the bytes).
# Uploading only the AAC track is identical in result and much less likely to
# drop mid-upload. Needs ffmpeg on PATH; silently falls back to the original.
_STRIP_TO_AAC = {".qta", ".mov"}


def _upload_source(audio_path: Path) -> tuple[Path, Path | None]:
    """Return (path_to_upload, tempfile_to_delete_or_None)."""
    if audio_path.suffix.lower() not in _STRIP_TO_AAC or not shutil.which("ffmpeg"):
        return audio_path, None
    tmp = Path(tempfile.gettempdir()) / f"stt_{audio_path.stem}_{int(time.time()*1000)}.m4a"
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(audio_path), "-map", "0:a:0", "-c", "copy", str(tmp)],
            check=True, capture_output=True, timeout=600,
        )
        if tmp.stat().st_size > 0:
            return tmp, tmp
    except Exception:
        pass
    tmp.unlink(missing_ok=True)
    return audio_path, None


_TRANSIENT = ("10053", "10054", "502", "503", "504", "Connection", "connection", "timed out", "Timeout")
_RETRY_DELAYS = (15, 45, 120)


def _transcribe_with_retry(transcriber: "aai.Transcriber", src: Path):
    """Upload + transcribe, retrying on transport-level failures (resets,
    aborted connections, gateway errors). A real API rejection is not retried."""
    last: Exception | None = None
    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            return transcriber.transcribe(str(src))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if delay is None or not any(t in msg for t in _TRANSIENT):
                raise
            last = exc
            time.sleep(delay)
    raise last  # pragma: no cover


def transcribe_file(
    audio_path: str | Path,
    *,
    model: str = DEFAULT_MODELS,
    speakers_expected: int | None = 2,
    language_code: str = "en",
    keyterms: list[str] | None = None,
) -> Transcript:
    """Transcribe one audio file with speaker diarization.

    model: comma-separated AssemblyAI speech model preference list (tried in order).
    speakers_expected: hint for the diarizer. Pass None to let it auto-detect.
    keyterms: names/jargon to bias recognition toward (AssemblyAI keyterms_prompt).
    """
    aai.settings.api_key = get_api_key()
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    config_kwargs: dict = {
        "speaker_labels": True,
        "language_code": language_code,
        "speech_models": _parse_models(model),
    }
    if speakers_expected:
        config_kwargs["speakers_expected"] = speakers_expected
    if keyterms:
        config_kwargs["keyterms_prompt"] = [k for k in keyterms if k.strip()]

    config = aai.TranscriptionConfig(**config_kwargs)
    transcriber = aai.Transcriber(config=config)

    src, tmp = _upload_source(audio_path)
    try:
        result = _transcribe_with_retry(transcriber, src)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    if result.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI transcription failed: {result.error}")

    return _build_transcript(result, audio_path, model)


def _build_transcript(result, audio_path: Path, model: str) -> Transcript:
    segments: list[Segment] = []
    speaker_order: list[str] = []

    utterances = result.utterances or []
    for i, utt in enumerate(utterances):
        speaker = str(utt.speaker) if utt.speaker is not None else "A"
        if speaker not in speaker_order:
            speaker_order.append(speaker)
        words = [
            Word(text=w.text, start=int(w.start), end=int(w.end))
            for w in (utt.words or [])
        ]
        segments.append(
            Segment(
                id=i,
                speaker=speaker,
                start=int(utt.start),
                end=int(utt.end),
                text=(utt.text or "").strip(),
                words=words,
            )
        )

    # Default display names: "Speaker 1", "Speaker 2", ... in first-appearance order.
    speaker_names = {
        key: f"Speaker {idx + 1}" for idx, key in enumerate(speaker_order)
    }

    duration_ms = int((result.audio_duration or 0) * 1000)
    now = _now_iso()
    return Transcript(
        audio_path=str(audio_path),
        audio_filename=audio_path.name,
        duration_ms=duration_ms,
        provider="assemblyai",
        model=model,
        speaker_names=speaker_names,
        segments=segments,
        created_at=now,
        modified_at=now,
    )
