<#
.SYNOPSIS
  Register (or remove) the Scheduled Task that keeps the STT web app online.

.DESCRIPTION
  The app binds 127.0.0.1:8792 and is exposed on the tailnet at :11443 via a
  persistent `tailscale serve --bg` mapping (already claimed; see
  docs/DEPLOY_TAILNET.md). This task just keeps the app process itself running
  across reboots. It launches the repo's own pythonw.exe directly (no console,
  no cmd redirect) and the app writes its own log to logs\webapp.log — that
  combination is what lets the task restart cleanly.

  Modeled on home_central_ai's verified HubWeb task.

.PARAMETER Uninstall
  Remove the task instead of registering it.

.PARAMETER Interactive
  Register a logon-only task (LogonType Interactive) that does NOT require an
  admin shell. It runs whenever you are logged on but does NOT survive a reboot
  that leaves you logged out. Use this for a quick setup; upgrade to the default
  (S4U) later from an admin shell for full boot survival.

.NOTES
  The default (S4U, survives reboot even logged out) MUST be registered from an
  ADMIN PowerShell — unelevated gives "Access is denied". See HUMAN_TODO.md.
#>
param(
    [switch]$Uninstall,
    [switch]$Interactive
)

$ErrorActionPreference = "Stop"
$TaskName = "SttWebApp"

# scripts\windows\install-webapp-task.ps1 -> repo root is two levels up.
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pyw = Join-Path $repo ".venv\Scripts\pythonw.exe"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'."
    } else {
        Write-Host "No scheduled task '$TaskName' found."
    }
    return
}

if (-not (Test-Path $pyw)) {
    throw "pythonw.exe not found at $pyw. Create the venv and install first (see README/HUMAN_TODO)."
}

$logonType = if ($Interactive) { "Interactive" } else { "S4U" }

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType $logonType -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
# No path in the argument string, so no extra quoting needed.
$action = New-ScheduledTaskAction -Execute $pyw -Argument "-m stt.webapp" -WorkingDirectory $repo
$triggers = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)
)

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' (LogonType $logonType)."
Write-Host "Start it now:   Start-ScheduledTask -TaskName $TaskName"
Write-Host "Check it:       Get-ScheduledTask $TaskName | Get-ScheduledTaskInfo"
if ($Interactive) {
    Write-Host "NOTE: Interactive task runs only while you are logged on. Re-run this"
    Write-Host "      script from an ADMIN shell (no -Interactive) for full boot survival."
}
