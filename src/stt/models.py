"""Transcript data model.

The JSON document produced here is the *source of truth* for a transcript. The
human-readable screenplay (.md/.txt) is always regenerated from it, so edits made
in the review editor never lose precise timing information.

Times are stored in integer milliseconds throughout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class Word:
    text: str
    start: int  # ms
    end: int  # ms

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Word":
        return cls(text=d["text"], start=int(d["start"]), end=int(d["end"]))


@dataclass
class Segment:
    """One diarized turn: a contiguous span attributed to a single speaker."""

    id: int
    speaker: str  # raw speaker key, e.g. "A", "B" (maps via Transcript.speaker_names)
    start: int  # ms
    end: int  # ms
    text: str
    words: list[Word] = field(default_factory=list)
    edited: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Segment":
        return cls(
            id=int(d["id"]),
            speaker=d["speaker"],
            start=int(d["start"]),
            end=int(d["end"]),
            text=d["text"],
            words=[Word.from_dict(w) for w in d.get("words", [])],
            edited=bool(d.get("edited", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "speaker": self.speaker,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "words": [asdict(w) for w in self.words],
            "edited": self.edited,
        }


@dataclass
class Transcript:
    audio_path: str  # path as given at transcription time (may be relative)
    audio_filename: str
    duration_ms: int
    provider: str
    model: str
    speaker_names: dict[str, str]  # {"A": "Speaker 1", "B": "Speaker 2"}
    segments: list[Segment]
    created_at: str
    modified_at: str
    schema_version: int = SCHEMA_VERSION

    # ---- serialization -------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "model": self.model,
            "audio_path": self.audio_path,
            "audio_filename": self.audio_filename,
            "duration_ms": self.duration_ms,
            "speaker_names": self.speaker_names,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Transcript":
        return cls(
            schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
            provider=d.get("provider", "assemblyai"),
            model=d.get("model", "unknown"),
            audio_path=d["audio_path"],
            audio_filename=d["audio_filename"],
            duration_ms=int(d.get("duration_ms", 0)),
            speaker_names=dict(d.get("speaker_names", {})),
            created_at=d.get("created_at", ""),
            modified_at=d.get("modified_at", ""),
            segments=[Segment.from_dict(s) for s in d.get("segments", [])],
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Transcript":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # ---- helpers -------------------------------------------------------

    def display_name(self, speaker_key: str) -> str:
        return self.speaker_names.get(speaker_key, speaker_key)
