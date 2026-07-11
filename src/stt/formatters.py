"""Render a Transcript to a human-readable screenplay.

Consecutive turns by the same speaker are merged into a single block, each block
prefixed with the timestamp of where that block starts.
"""

from __future__ import annotations

from .models import Transcript


def format_timestamp(ms: int) -> str:
    """Milliseconds -> [HH:MM:SS] (hours dropped only when zero)."""
    total_seconds = ms // 1000
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def to_screenplay(transcript: Transcript) -> str:
    """Produce the .md/.txt screenplay text."""
    lines: list[str] = []
    lines.append(f"# Transcript: {transcript.audio_filename}")
    lines.append("")

    # Speaker legend (only if names have been customized or there are multiple).
    speakers = _ordered_speakers(transcript)
    if speakers:
        legend = ", ".join(transcript.display_name(s) for s in speakers)
        lines.append(f"_Speakers: {legend}_")
        lines.append("")

    for block in _merge_consecutive(transcript):
        speaker, start_ms, text = block
        ts = format_timestamp(start_ms)
        name = transcript.display_name(speaker)
        lines.append(f"[{ts}] **{name}:** {text}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _ordered_speakers(transcript: Transcript) -> list[str]:
    seen: list[str] = []
    for seg in transcript.segments:
        if seg.speaker not in seen:
            seen.append(seg.speaker)
    return seen


def _merge_consecutive(transcript: Transcript) -> list[tuple[str, int, str]]:
    """Merge adjacent same-speaker segments -> (speaker, start_ms, joined_text)."""
    blocks: list[tuple[str, int, str]] = []
    for seg in transcript.segments:
        text = seg.text.strip()
        if not text:
            continue
        if blocks and blocks[-1][0] == seg.speaker:
            prev_speaker, prev_start, prev_text = blocks[-1]
            blocks[-1] = (prev_speaker, prev_start, f"{prev_text} {text}")
        else:
            blocks.append((seg.speaker, seg.start, text))
    return blocks
