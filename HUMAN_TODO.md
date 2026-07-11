# HUMAN_TODO — things only you can do

The tool is built and tested. These are the bits that need your hands (mostly the
API key). Do them once and you're set.

## 1. Get an AssemblyAI API key

1. Sign up at **https://www.assemblyai.com/** (email or Google).
2. Open the **Dashboard → API Keys** and copy your key.
3. Billing is **pay-as-you-go** — no subscription. New accounts get **$50 free
   credit**, which for your use (English, ~2 speakers) is a *lot* of audio
   (transcription + diarization is roughly **$0.15–0.20 per hour** of audio).
   When the free credit runs out, add a card and top up; you're only billed for
   seconds of audio actually processed.

> Why AssemblyAI and not OpenAI: OpenAI's transcription models don't label
> speakers. AssemblyAI does diarization in the same call, which is the whole
> point here. If you ever want to switch providers, the seam is
> `src/stt/transcribe.py` — everything else is provider-agnostic.

## 2. Put the key where the tool can find it

Easiest — a `.env` file in the project root:

```bash
cp .env.example .env
# then edit .env and paste your key after ASSEMBLYAI_API_KEY=
```

Or set it as an environment variable (PowerShell, persists for new terminals):

```powershell
setx ASSEMBLYAI_API_KEY "your-key-here"
```

`.env` is gitignored, so your key won't be committed.

## 3. Install the tool (one time)

From the project root (`C:\Users\Stephen\Documents\GitHub\stt_misc`):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

(If you'd rather not activate the venv each time, call `.venv\Scripts\stt.exe …`.)

## 4. Smoke-test it on one real recording

```powershell
stt transcribe "C:\path\to\one-recording.m4a" "transcripts\one-recording.md" --review
```

This transcribes the file and immediately opens the correction editor in your
browser. Confirm playback works and speaker labels look sane.

## 5. Browser note (m4a playback)

The editor plays audio in your browser. **Use Chrome or Edge** — both play `.m4a`
(AAC) natively. Firefox sometimes won't play AAC. `.mp3`/`.wav` work everywhere.
If audio ever won't load for a specific file, converting it to mp3 first is the
fallback (I can add an auto-convert step later if it comes up).

## That's everything

Once the key is set and `pip install -e .` has run, you never need to touch this
file again. Day-to-day usage is in **README.md**.
