"""Command-line interface.

    stt transcribe INPUT OUTPUT   Transcribe one audio file -> screenplay (+ JSON).
    stt review PATH               Open the web editor to correct a transcript.
    stt batch INDIR OUTDIR        Transcribe a whole folder (resumable).
    stt export PATH [OUTPUT]      Regenerate the screenplay from an edited JSON.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import sidecar_json_path
from .formatters import to_screenplay
from .models import Transcript


def _resolve_speakers(args) -> int | None:
    if getattr(args, "auto_speakers", False):
        return None
    return args.speakers


def cmd_transcribe(args) -> int:
    from .config import get_api_key
    from .transcribe import transcribe_file

    get_api_key()  # fail fast with a clear message before doing any work
    audio = Path(args.input)
    output = Path(args.output)
    if output.suffix.lower() not in {".md", ".txt"}:
        output = output.with_suffix(".md")
    json_path = sidecar_json_path(output)

    print(f"Transcribing {audio.name} … (this uploads to AssemblyAI and may take a bit)")
    transcript = transcribe_file(
        audio, model=args.model, speakers_expected=_resolve_speakers(args)
    )

    transcript.save(json_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(to_screenplay(transcript), encoding="utf-8")

    mins = transcript.duration_ms / 60000
    print(f"  {len(transcript.segments)} turns, {len(transcript.speaker_names)} speaker(s), "
          f"{mins:.1f} min of audio.")
    print(f"  Screenplay: {output}")
    print(f"  Data (edit source of truth): {json_path}")

    if args.review:
        return _launch_review(json_path, output, audio_override=str(audio),
                              port=args.port, open_browser=not args.no_browser)
    else:
        print(f"\nTo correct it:  stt review \"{output}\"")
    return 0


def _resolve_review_paths(path: Path) -> tuple[Path, Path]:
    """Given a .json or a screenplay path, return (json_path, screenplay_path)."""
    if path.suffix.lower() == ".json":
        return path, path.with_suffix(".md")
    return sidecar_json_path(path), path


def _launch_review(json_path: Path, screenplay_path: Path, *, audio_override, port, open_browser) -> int:
    from .review.server import serve

    if not json_path.exists():
        print(f"No transcript data found at {json_path}.\n"
              f"Run `stt transcribe` on the audio first.", file=sys.stderr)
        return 1
    try:
        serve(json_path, screenplay_path, audio_override=audio_override,
              port=port, open_browser=open_browser)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_review(args) -> int:
    json_path, screenplay_path = _resolve_review_paths(Path(args.path))
    return _launch_review(
        json_path, screenplay_path,
        audio_override=args.audio, port=args.port, open_browser=not args.no_browser,
    )


def cmd_batch(args) -> int:
    from .batch import run_batch

    return run_batch(
        args.input_dir, args.output_dir,
        model=args.model,
        speakers_expected=_resolve_speakers(args),
        concurrency=args.concurrency,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )


def cmd_export(args) -> int:
    json_path, default_out = _resolve_review_paths(Path(args.path))
    if json_path.suffix.lower() != ".json":
        json_path = sidecar_json_path(Path(args.path))
    if not json_path.exists():
        print(f"No transcript JSON at {json_path}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else default_out
    transcript = Transcript.load(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_screenplay(transcript), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


def _add_speaker_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--speakers", type=int, default=2,
                   help="Expected number of speakers (hint for diarization). Default: 2.")
    p.add_argument("--auto-speakers", action="store_true",
                   help="Let the diarizer auto-detect the number of speakers.")
    p.add_argument("--model", default="universal",
                   help="AssemblyAI speech model (default: universal).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stt", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    t = sub.add_parser("transcribe", help="Transcribe one audio file.")
    t.add_argument("input", help="Path to the audio file (.m4a/.mp3/.wav/…).")
    t.add_argument("output", help="Path to the screenplay output (.md).")
    _add_speaker_args(t)
    t.add_argument("--review", action="store_true",
                   help="Open the editor immediately after transcribing.")
    t.add_argument("--port", type=int, default=5005)
    t.add_argument("--no-browser", action="store_true",
                   help="Don't auto-open the browser (with --review).")
    t.set_defaults(func=cmd_transcribe)

    r = sub.add_parser("review", help="Open the web editor for a transcript.")
    r.add_argument("path", help="The screenplay (.md) or data (.json) path.")
    r.add_argument("--audio", help="Override the audio file path if it moved.")
    r.add_argument("--port", type=int, default=5005)
    r.add_argument("--no-browser", action="store_true")
    r.set_defaults(func=cmd_review)

    b = sub.add_parser("batch", help="Transcribe a folder of audio (resumable).")
    b.add_argument("input_dir", help="Folder containing audio files (searched recursively).")
    b.add_argument("output_dir", help="Folder to write transcripts into (tree mirrored).")
    _add_speaker_args(b)
    b.add_argument("--concurrency", type=int, default=3,
                   help="How many files to process at once (default: 3).")
    b.add_argument("--overwrite", action="store_true",
                   help="Re-transcribe files even if output already exists.")
    b.add_argument("--dry-run", action="store_true",
                   help="List what would be done and estimate cost; transcribe nothing.")
    b.set_defaults(func=cmd_batch)

    e = sub.add_parser("export", help="Regenerate the screenplay from an edited JSON.")
    e.add_argument("path", help="The .json (or its .md sibling) to export from.")
    e.add_argument("output", nargs="?", help="Output screenplay path (default: sibling .md).")
    e.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
