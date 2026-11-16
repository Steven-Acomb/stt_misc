<#
.SYNOPSIS
  Copy transcript .md files per week folder to Google Drive.

  Source: transcripts\sphere_week_by_week\week_N\*.md
  Dest:   G:\My Drive\sphere_voice_memos\transcripts\week_N\

  Only .md files; .json / manifest.csv stay local. Existing Drive files are
  overwritten only if the local copy is newer (robocopy default). Never deletes.

.EXAMPLE
  .\scripts\windows\copy-md-to-drive.ps1              # all week_* folders
  .\scripts\windows\copy-md-to-drive.ps1 -Weeks 4,5,8  # just these
#>
param(
  [int[]]$Weeks,
  [string]$Source = (Join-Path $PSScriptRoot "..\..\transcripts\sphere_week_by_week"),
  [string]$Dest = "G:\My Drive\sphere_voice_memos\transcripts"
)
$Source = (Resolve-Path $Source).Path
if (-not (Test-Path $Dest)) { throw "Drive folder not found: $Dest (is Google Drive running?)" }

$folders = Get-ChildItem $Source -Directory -Filter "week_*"
if ($Weeks) { $folders = $folders | Where-Object { $Weeks -contains [int]($_.Name -replace 'week_', '') } }

$total = 0
foreach ($f in $folders | Sort-Object { [int]($_.Name -replace 'week_', '') }) {
  $n = (Get-ChildItem $f.FullName -Filter *.md -File | Measure-Object).Count
  if ($n -eq 0) { continue }
  $target = Join-Path $Dest $f.Name
  robocopy $f.FullName $target *.md /NJH /NJS /NDL /NFL /NP /R:2 /W:2 | Out-Null
  $onDrive = (Get-ChildItem $target -Filter *.md -File | Measure-Object).Count
  "{0,-10} {1,3} local .md -> {2,3} on Drive" -f $f.Name, $n, $onDrive
  $total += $n
}
"done: $total .md files across $(@($folders).Count) week folder(s) -> $Dest"
# robocopy returns 1 for "files copied"; do not let that read as a failure
exit 0
