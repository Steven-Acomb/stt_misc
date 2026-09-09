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

## 6. Make the phone web app survive reboots (admin PowerShell, one time)

**Why this is yours:** the web app that serves your phone
(`https://stephen-desktop.tail796bf2.ts.net:11443/`) is kept alive by a Windows
Scheduled Task. Registering the *full* version — the one that comes back after a
reboot even when you're logged out (LogonType S4U) — requires an **elevated**
PowerShell; an unelevated shell fails with "Access is denied". Registering a task
is something only you can authorize, so it can't be automated for you.

Until you do this, the app only stays up while something is actively running it
(a `python -m stt.webapp` you started, or a Claude session) — it will **not**
restart itself or come back after a reboot. This step makes it permanent.
(Registering the task needs elevation on this machine even for the logon-only
`-Interactive` variant, so there's no non-admin shortcut — the admin shell below
is the path.)

**Steps:**
1. Press **Win+X**, choose **Terminal (Admin)** (accept the UAC prompt).
2. Run these (they work whether the admin terminal is PowerShell **or** Command
   Prompt — `schtasks` is native to both, unlike the `*-ScheduledTask` cmdlets):
   ```
   cd C:\Users\Stephen\Documents\GitHub\stt_misc
   powershell -ExecutionPolicy Bypass -File scripts\windows\install-webapp-task.ps1
   schtasks /run /tn SttWebApp
   ```
3. Confirm it's serving (run each on its own line — no trailing comments, or cmd
   passes them to curl):
   ```
   schtasks /query /tn SttWebApp
   curl http://localhost:8792/api/health
   ```
   The task **Status** should read `Running`, and the curl should print
   `{"ok":true}`.

That's it — the app now starts on every boot/logon and restarts itself if it
crashes. To undo: `... install-webapp-task.ps1 -Uninstall`. Full details in
`docs/DEPLOY_TAILNET.md`.

## That's everything

Day-to-day usage is in **README.md**; tailnet/deploy details in
`docs/DEPLOY_TAILNET.md`.
