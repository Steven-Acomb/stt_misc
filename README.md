# stt_misc — speech-to-text with speakers, a correction editor, and a phone web app

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
- **Phone/web app** — browse or upload audio, transcribe, review, and download
  transcripts from your phone over Tailscale (`python -m stt.webapp`).

Two ways to use it: the **CLI** (`stt …`, desktop) and the **web app**
(`python -m stt.webapp`, desktop or phone). They share the same transcripts.

First-time setup (install, API key) is in **[docs/SETUP.md](docs/SETUP.md)**;
things that need you specifically over time live in **[HUMAN_TODO.md](HUMAN_TODO.md)**.

## Web app (browse · upload · transcribe · review · download)

Start the server:

```powershell
python -m stt.webapp
```

Then open **http://localhost:8792/**. It's a plain desktop page here, and the
same app on your phone over Tailscale (below). Three tabs:

- **New** — browse this machine's files, **or upload** an audio file from your
  device (on iOS the picker opens the Files app), set the speaker count, and
  Start. Transcription runs in the background.
- **Jobs** — live status of running transcriptions; tap a finished one to review.
- **Transcripts** — every transcript; tap to open the full editor, or
  **⬇ Download .md** to save it to your device.

The editor has the same controls as the desktop one (playback, tap-a-timestamp
to seek, fix text, reassign/rename speakers, merge/split, autosave), plus
**Download .md / .json** buttons (the `.md` one saves your edits first).

- Binds `127.0.0.1:8792`, no login (the tailnet is the security boundary).
- Env overrides: `STT_WEB_PORT`, `STT_WEB_HOST`, `STT_TRANSCRIPTS_DIR`,
  `STT_UPLOAD_DIR`, `STT_WEB_WORKERS`. Writes its own log to `logs/webapp.log`.
- Transcription jobs live in memory — restarting the server drops in-flight
  jobs (finished transcripts are already on disk). Kick a dropped one off again.

### On your phone (Tailscale)

Served at **`https://stephen-desktop.tail796bf2.ts.net:11443/`** — open it with
Tailscale connected and "Add to Home Screen" for an installable app. To keep it
running across reboots it runs as a Windows scheduled task (`SttWebApp`).
Full setup, the `tailscale serve` claim, and the always-online task (needs one
admin command from you) are in **[docs/DEPLOY_TAILNET.md](docs/DEPLOY_TAILNET.md)**.

## CLI: get one transcript right

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
| `python -m stt.webapp` | Start the phone/web app on `127.0.0.1:8792` (see the Web app section). |

If a Windows "Application Control policy" ever blocks the generated `stt.exe`
launcher, run the CLI as `python -m stt.cli …` (identical commands).

## Project layout

```
src/stt/
  cli.py            # argparse CLI
  transcribe.py     # AssemblyAI integration (the provider seam)
  models.py         # Transcript/Segment/Word + JSON load/save
  formatters.py     # JSON -> screenplay
  batch.py          # folder processing
  review/           # desktop editor (stt review)
    server.py       #   Flask app (API + audio streaming with Range support)
    static/         #   index.html, app.js, style.css (the editor UI)
  webapp/           # phone/web app (python -m stt.webapp), served over Tailscale
    app.py          #   FastAPI: fs browse, upload, jobs, transcript CRUD, download, audio
    jobs.py         #   async transcription job queue
    __main__.py     #   uvicorn entrypoint (127.0.0.1:8792)
    static/         #   the mobile PWA (index.html, app.js, style.css, manifest, icons)
scripts/windows/
  install-webapp-task.ps1   # register / -Uninstall the always-online scheduled task
docs/
  SETUP.md          # fresh-clone install
  DEPLOY_TAILNET.md # tailnet serve + keeping the web app online
```
