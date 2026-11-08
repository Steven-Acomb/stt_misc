"""Batch transcription over a folder of audio files.

Deprioritized relative to the single-file "get one right" workflow, but useful
for churning through a backlog. Skips files whose output already exists so runs
are resumable, processes several files concurrently, estimates cost up front,
and writes a manifest CSV.
"""

from __future__ import annotations

import csv
import re
import sys
from collections.abc import Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import AUDIO_EXTENSIONS, COST_PER_HOUR_USD, sidecar_json_path
from .formatters import to_screenplay
from .transcribe import transcribe_file


def probe_duration_seconds(path: Path) -> float | None:
    """Best-effort audio duration via mutagen (no external binaries)."""
    try:
        from mutagen import File as MutagenFile

        mf = MutagenFile(str(path))
        if mf is not None and mf.info is not None:
            return float(mf.info.length)
    except Exception:
        pass
    return None


def _is_junk(p: Path) -> bool:
    """macOS zip droppings: __MACOSX folders and ._ resource-fork stubs."""
    return p.name.startswith("._") or "__MACOSX" in p.parts


def discover_audio(input_dir: Path) -> list[Path]:
    files = [
        p for p in sorted(input_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS and not _is_junk(p)
    ]
    return files


# ---- ingest helpers: flat, date-prefixed names + speaker hint from the name ----
_DATE_IN_NAME = re.compile(r"(?<!\d)(\d{1,2})-(\d{1,2})-(\d{2}|\d{4})(?!\d)")
_TWO_PARTY = re.compile(r"\b(convo|call|chat|brief|meeting|1[_:]1|coffee|dinner|lunch)\b", re.I)


def date_prefix_for(audio: Path) -> str:
    """YYYY-MM-DD from an MM-DD-YY in the file name, else "undated" (an mtime
    would be the download/copy time, which lies about when it was recorded)."""
    m = _DATE_IN_NAME.search(audio.stem)
    if m:
        mm, dd, yy = (int(x) for x in m.groups())
        if yy < 100:
            yy += 2000
        try:
            return datetime(yy, mm, dd).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return "undated"


def flat_dated_stem(audio: Path) -> str:
    return f"{date_prefix_for(audio)} {audio.stem}"


def speakers_from_name(audio: Path, default: int | None = None) -> int | None:
    """2 for something that reads like a one-on-one, else `default` (None = auto)."""
    return 2 if _TWO_PARTY.search(audio.stem) else default


def output_paths_for(
    audio: Path, input_dir: Path, output_dir: Path, suffix: str = "",
    stem_fn: Callable[[Path], str] | None = None,
) -> tuple[Path, Path]:
    """Return (screenplay_md, json) for an input file.

    Default: mirror the input tree under output_dir. With stem_fn, write flat
    into output_dir using stem_fn(audio) as the name. suffix is appended to the
    stem (e.g. "_UNREVIEWED_MESSY_TRANSCRIPT") so the name flags its state.
    """
    if stem_fn:
        md_path = output_dir / (stem_fn(audio) + suffix + ".md")
    else:
        rel = audio.relative_to(input_dir)
        md_path = output_dir / rel.with_name(rel.stem + suffix + ".md")
    return md_path, sidecar_json_path(md_path)


def estimate_cost(files: list[Path]) -> tuple[float, float]:
    """Return (total_hours, est_usd). Files with unknown duration count as 0."""
    total_seconds = 0.0
    for f in files:
        dur = probe_duration_seconds(f)
        if dur:
            total_seconds += dur
    hours = total_seconds / 3600.0
    return hours, hours * COST_PER_HOUR_USD


def run_batch(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    model: str = "universal",
    speakers_expected: int | None = 2,
    concurrency: int = 3,
    overwrite: bool = False,
    dry_run: bool = False,
    suffix: str = "",
    stem_fn: Callable[[Path], str] | None = None,
    speakers_fn: Callable[[Path], int | None] | None = None,
    keyterms: list[str] | None = None,
) -> int:
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()
    if not input_dir.is_dir():
        print(f"Input directory not found: {input_dir}", file=sys.stderr)
        return 1

    all_files = discover_audio(input_dir)
    if not all_files:
        print(f"No audio files found under {input_dir}")
        return 0

    pending: list[tuple[Path, Path, Path]] = []
    skipped = 0
    for audio in all_files:
        md_path, json_path = output_paths_for(audio, input_dir, output_dir, suffix, stem_fn)
        if not overwrite and md_path.exists() and json_path.exists():
            skipped += 1
            continue
        pending.append((audio, md_path, json_path))

    hours, est = estimate_cost([p[0] for p in pending])
    print(f"Found {len(all_files)} audio file(s); {skipped} already done, {len(pending)} to process.")
    print(f"Estimated audio: {hours:.2f} h  ->  ~${est:.2f} (rough).")

    if dry_run:
        for audio, md_path, _ in pending:
            spk = speakers_fn(audio) if speakers_fn else speakers_expected
            print(f"  would transcribe [{spk or 'auto'} spk]: {audio.name}  ->  {md_path.name}")
        return 0

    if not pending:
        print("Nothing to do.")
        return 0

    manifest_path = output_dir / "manifest.csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    def work(item: tuple[Path, Path, Path]) -> dict:
        audio, md_path, json_path = item
        try:
            transcript = transcribe_file(
                audio, model=model,
                speakers_expected=speakers_fn(audio) if speakers_fn else speakers_expected,
                keyterms=keyterms,
            )
            json_path.parent.mkdir(parents=True, exist_ok=True)
            transcript.save(json_path)
            md_path.write_text(to_screenplay(transcript), encoding="utf-8")
            return {
                "audio": str(audio),
                "output": str(md_path),
                "status": "ok",
                "duration_s": round(transcript.duration_ms / 1000, 1),
                "speakers": len(transcript.speaker_names),
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001 - record and continue the batch
            return {
                "audio": str(audio),
                "output": str(md_path),
                "status": "error",
                "duration_s": "",
                "speakers": "",
                "error": str(exc),
            }

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(work, item): item for item in pending}
        for fut in as_completed(futures):
            row = fut.result()
            rows.append(row)
            done += 1
            status = row["status"]
            mark = "ok " if status == "ok" else "ERR"
            print(f"  [{done}/{len(pending)}] {mark} {Path(row['audio']).name}"
                  + (f"  ({row['error']})" if status == "error" else ""))

    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["audio", "output", "status", "duration_s", "speakers", "error"]
        )
        writer.writeheader()
        writer.writerows(rows)

    errors = sum(1 for r in rows if r["status"] == "error")
    print(f"\nDone. {len(rows) - errors} ok, {errors} error(s). Manifest: {manifest_path}")
    return 1 if errors else 0
