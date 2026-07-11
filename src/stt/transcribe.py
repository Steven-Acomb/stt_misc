"""AssemblyAI transcription: audio file -> Transcript (with speaker diarization)."""

from __future__ import annotations

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


def transcribe_file(
    audio_path: str | Path,
    *,
    model: str = DEFAULT_MODELS,
    speakers_expected: int | None = 2,
    language_code: str = "en",
) -> Transcript:
    """Transcribe one audio file with speaker diarization.

    model: comma-separated AssemblyAI speech model preference list (tried in order).
    speakers_expected: hint for the diarizer. Pass None to let it auto-detect.
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

    config = aai.TranscriptionConfig(**config_kwargs)
    transcriber = aai.Transcriber(config=config)

    result = transcriber.transcribe(str(audio_path))
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
