# Deploying the STT web app on the tailnet

The web app (`python -m stt.webapp`) lets you browse this desktop's files,
transcribe them, and review/correct transcripts — from your phone, over
Tailscale, from anywhere. This documents how it's exposed and kept online.

Machine-wide Tailscale rules live in the canonical guide
`C:\Users\Stephen\Documents\GitHub\home_central_ai\docs\TAILSCALE.md` — read that
before changing any `tailscale serve` config. **Never** `tailscale serve reset`,
**never** touch the root `/` on 443 (the podcast).

## Ports (claimed for this app)

| | |
|---|---|
| Local bind | `127.0.0.1:8792` (never `0.0.0.0`) |
| Tailnet HTTPS | `11443` → `https://stephen-desktop.tail796bf2.ts.net:11443/` |
| Serve claim | `tailscale serve --bg --https=11443 localhost:8792` |

`--bg` makes the serve mapping persist across reboots (verified on this machine).
To remove **only** this mapping: `tailscale serve --https=11443 off`.

## Security posture

No app-level auth — the **tailnet is the boundary**, same as the other apps on
this box. The file browser can see the whole disk (deliberate), but the media
endpoint only serves audio files, and there are no write/delete-to-disk
endpoints beyond saving transcript edits into `transcripts\`. Don't add
secret-bearing or destructive endpoints without thinking about who's on the tailnet.

## On the phone

1. Tailscale app installed and connected (same tailnet, `acomb.stephen@gmail.com`).
2. Open `https://stephen-desktop.tail796bf2.ts.net:11443/` in Safari/Chrome.
3. "Add to Home Screen" → it installs as a standalone PWA (dark, full-screen).

## Keeping it online (Scheduled Task)

The app runs as a Scheduled Task so it survives reboots. Install/remove with
`scripts\windows\install-webapp-task.ps1`:

- **Full (survives reboot even logged out)** — needs an **admin** PowerShell:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\windows\install-webapp-task.ps1
  Start-ScheduledTask -TaskName SttWebApp
  ```
- **Logon-only fallback (no admin)** — runs whenever you're logged in:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\windows\install-webapp-task.ps1 -Interactive
  Start-ScheduledTask -TaskName SttWebApp
  ```
- **Remove:** `... install-webapp-task.ps1 -Uninstall`

The task launches `.venv\Scripts\pythonw.exe -m stt.webapp` directly (no console,
no `cmd >> log` wrapper) with the repo as the working directory (so `.env` — and
thus the AssemblyAI key — is picked up). The app writes its own log to
`logs\webapp.log`, opened per write.

## Verify / troubleshoot

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" serve status   # 11443 -> localhost:8792 present?
curl http://localhost:8792/api/health                        # app answering?
Get-ScheduledTask SttWebApp | Get-ScheduledTaskInfo          # task Running?
Get-Content logs\webapp.log -Tail 20                         # recent app log
```

A live serve mapping with nothing behind it returns a connection error — check
the task/app before suspecting Tailscale. If two instances fight over 8792
(e.g. a manual `python -m stt.webapp` plus the task), stop one.
