# stt_misc — speech-to-text with speakers, plus a correction editor

Turn phone voice recordings (`.m4a`, `.mp3`, …) into speaker-labeled transcripts,
then **listen and correct them side-by-side** in a local web editor until they're
exactly right.

- **Transcription + speaker diarization** via [AssemblyAI](https://www.assemblyai.com/)
  (pay-as-you-go, ~$0.15–0.20/hr of audio, does "Speaker 1 / Speaker 2" natively).
- **Correction editor** — a local browser app: play the audio, watch the current
  line highlight, click a timestamp to jump, fix text, reassign/rename speakers,
  and merge/split turns. Everything autosaves.
- **Screenplay output** (`.md`) with timestamps, backed by a JSON source-of-truth
  so timing survives edits.
- **Batch mode** for churning through a backlog (resumable, cost estimate).

First-time setup (API key, install) is in **[HUMAN_TODO.md](HUMAN_TODO.md)**.

## The main workflow: get one transcript right

```powershell
# 1. Transcribe one file and open the editor immediately:
stt transcribe "recordings\call.m4a" "transcripts\call.md" --review

# ...correct it in the browser (it autosaves; Ctrl+S to save now)...

# 2. Reopen the editor on it any time:
stt review "transcripts\call.md"
```

The transcript defaults to hinting **2 speakers**. Override per file:

```powershell
stt transcribe in.m4a out.md --speakers 3      # hint 3 speakers
stt transcribe in.m4a out.md --auto-speakers   # let it auto-detect
```

### In the editor

| Action | How |
|---|---|
| Play / pause | `Space` (when not typing) or `Alt`+`K` (anywhere) |
| Back / forward 3s | `Alt`+`J` / `Alt`+`L` |
| Jump audio to a line | Click its timestamp |
| Fix wording | Just type in the line |
| Reassign a turn's speaker | The dropdown on the left of the turn |
| Rename a speaker everywhere | Edit the name in the **Speakers** bar up top |
| Add a new speaker | Pick "+ New speaker…" in a turn's dropdown |
| Merge a turn into the next | **Merge ↓** on the turn |
| Split a turn | Put the cursor where the text should split, position the audio
  playhead at the moment it should split, then **Split** |
| Change speed | The **Speed** selector (0.5×–2×) |
| Save | Autosaves ~2s after you stop; `Ctrl`+`S` to force |

The playing line auto-scrolls into view — but never while you're editing text, so
it won't yank your cursor around.

## Batch mode (backlog)

Deprioritized but there when you want it. Mirrors the input folder tree into the
output folder, **skips files already done** (resumable), and writes a
`manifest.csv`.

```powershell
# See what would run and what it'd cost — transcribes nothing:
stt batch "recordings" "transcripts" --dry-run

# Actually run it (3 files at a time):
stt batch "recordings" "transcripts" --concurrency 3
```

Then correct any individual result with `stt review "transcripts\<name>.md"`.

## Output files

For `out.md` you get two files:

- **`out.md`** — the readable screenplay you keep. Regenerated from the JSON on
  every save.
  ```
  [00:00:03] **Speaker 1:** Hey, did you review the proposal?
  [00:00:09] **Speaker 2:** Yeah, I read it last night. A couple thoughts.
  ```
- **`out.json`** — the source of truth: every turn with speaker, millisecond
  timings, and word-level timings. This is what the editor reads/writes and what
  any future tooling should build on.

Edited the JSON by hand or with a script? Regenerate the screenplay:

```powershell
stt export "transcripts\call.json"
```

## Commands

| Command | Purpose |
|---|---|
| `stt transcribe IN OUT` | Transcribe one file → screenplay + JSON. Add `--review` to open the editor. |
| `stt review PATH` | Open the editor for a `.md` or `.json`. `--audio PATH` if the audio moved. |
| `stt batch INDIR OUTDIR` | Transcribe a folder (resumable). `--dry-run`, `--overwrite`, `--concurrency N`. |
| `stt export PATH [OUT]` | Regenerate the screenplay from an edited JSON. |

## Project layout

```
src/stt/
  cli.py            # argparse CLI
  transcribe.py     # AssemblyAI integration (the provider seam)
  models.py         # Transcript/Segment/Word + JSON load/save
  formatters.py     # JSON -> screenplay
  batch.py          # folder processing
  review/
    server.py       # Flask app (API + audio streaming with Range support)
    static/         # index.html, app.js, style.css (the editor UI)
```
