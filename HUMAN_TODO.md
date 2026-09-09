# HUMAN_TODO — what's done, what's in YOUR court

The running list of things in stt_misc that need **you specifically** — decisions
only you can make, and human-only actions (admin shells, external-account setup).
Agents do the building; anything they need from you lands here, and gets checked
off when done. Done items collapse into the ledger over time; open items sit in
"your court" with a full walk-through each.

This is **not** a setup tutorial — fresh-clone install lives in `docs/SETUP.md`.
Claude's build queue isn't here either.

---

## Part 1 — ✅ DONE (the ledger)

| When | What |
|---|---|
| 2026-07 | AssemblyAI account + API key created; key saved in `.env` (`ASSEMBLYAI_API_KEY`) |
| 2026-07 | First real transcriptions run and corrected in the desktop editor |
| 9/09 | Smart App Control turned off so the pip-generated `stt.exe` launcher stops being blocked by an Application Control policy |
| 9/09 | **Phone web app made always-online** — `SttWebApp` scheduled task registered S4U from an admin shell; live at `https://stephen-desktop.tail796bf2.ts.net:11443/`, survives reboot (walk-through kept below) |

---

## Part 2 — YOUR COURT

**Still open: nothing right now.** New human-only items (decisions, admin shells,
external-account setup) will appear here as agents hit them.

Optional / your call:
- **Reboot once to watch the web app come back on its own.** The S4U task pattern
  is already reboot-verified on this machine, so this is just to see it for
  yourself — no action needed otherwise.

✅ done, kept for reference: the admin task registration (below).

### ✅ Register the always-online web-app task — admin shell *(done 9/09)*

**Why it's yours:** registering an **S4U** scheduled task (one that survives a
reboot even when you're logged out) needs an **elevated** shell — unelevated
fails with "Access is denied". This is the one human-only step that makes the
phone web app permanent. Keep this for re-registration (fresh clone / new
machine) or if the task ever gets removed.

1. **Win+X → Terminal (Admin)** (accept the UAC prompt).
2. Run (works in Command Prompt **or** PowerShell — `schtasks` is native to both,
   unlike the `*-ScheduledTask` cmdlets):
   ```
   cd C:\Users\Stephen\Documents\GitHub\stt_misc
   powershell -ExecutionPolicy Bypass -File scripts\windows\install-webapp-task.ps1
   schtasks /run /tn SttWebApp
   ```
3. Confirm (each on its own line — no trailing `#` comments, or cmd feeds them to
   curl):
   ```
   schtasks /query /tn SttWebApp
   curl http://localhost:8792/api/health
   ```
   **Status** should read `Running`; the curl should print `{"ok":true}`.

Undo: `... install-webapp-task.ps1 -Uninstall`. Full deploy details:
`docs/DEPLOY_TAILNET.md`.

---

## Reference

- Fresh install / how to run — `docs/SETUP.md`
- Put the web app on the tailnet / keep it online — `docs/DEPLOY_TAILNET.md`
- Day-to-day usage — `README.md`
