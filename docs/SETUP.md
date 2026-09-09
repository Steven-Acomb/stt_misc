# Setup — stt_misc (fresh clone → working)

Stateless install guide: everything needed to get stt_misc running on a new
machine or a fresh clone. For what needs **you specifically** over time
(decisions, admin steps), see `HUMAN_TODO.md` — this doc is not that.

## Prerequisites

- **Python 3.10+** (`python --version`).
- A **Chromium browser** (Chrome/Edge) for the transcript editor — they play
  `.m4a` (AAC) natively; Firefox often won't. `.mp3`/`.wav` work everywhere.

## 1. Code + environment

```powershell
cd C:\Users\Stephen\Documents\GitHub\stt_misc
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

- If PowerShell blocks activation: run once
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- If a Windows **Application Control policy** blocks the generated `stt.exe`
  launcher, just call the CLI as **`python -m stt.cli ...`** (identical commands).

## 2. AssemblyAI API key

Transcription uses [AssemblyAI](https://www.assemblyai.com/) — pay-as-you-go
(~$0.15–0.20/hr of audio), and it does speaker diarization in the same call
(the whole reason it's not OpenAI; the provider seam is `src/stt/transcribe.py`).

Get a key at the site → Dashboard → API Keys, then put it in a `.env` in the
repo root (gitignored):

```powershell
copy .env.example .env    # then edit: ASSEMBLYAI_API_KEY=<your key>
```

## 3. Use the CLI

```powershell
stt transcribe "C:\path\to\recording.m4a" "transcripts\recording.md" --review
```

Transcribes and opens the desktop correction editor. Full command list
(transcribe / review / batch / export) is in `README.md`.

## 4. Run the phone-friendly web app

```powershell
python -m stt.webapp
```

Serves at `http://localhost:8792/` — browse or upload audio, transcribe in the
background, review/correct transcripts. To reach it from your phone over
Tailscale and keep it always-on, follow `docs/DEPLOY_TAILNET.md`.
