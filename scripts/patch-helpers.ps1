$global:CF_ROOT = (Get-Location).Path
if (-not (Test-Path (Join-Path $global:CF_ROOT "backend\main.py"))) { throw "Project root me chalayein (jahan backend, frontend, scripts folders hain)." }
$global:CF_UTF8 = New-Object System.Text.UTF8Encoding($false)

function CF-Backup([string]$full) {
  if (-not (Test-Path $full)) { return }
  $dir = Join-Path $global:CF_ROOT "logs\backup_phase3"
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $rel = $full.Substring($global:CF_ROOT.Length).TrimStart('\')
  $dest = Join-Path $dir ($rel -replace '[\\/:]', '__')
  if (-not (Test-Path $dest)) { Copy-Item $full $dest }
}

function Write-ProjectFile([string]$Path, [string]$Content, [switch]$GuardPlaceholder) {
  $full = Join-Path $global:CF_ROOT $Path
  $dir = Split-Path $full -Parent
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  if ($GuardPlaceholder -and (Test-Path $full)) {
    $old = [IO.File]::ReadAllText($full)
    if (($old -notmatch 'PlaceholderPage') -and ($old -notmatch 'CLIPFORGE-PHASE3')) {
      Write-Host "SKIP (aapne ye file customize ki hai): $Path" -ForegroundColor Yellow
      return
    }
  }
  CF-Backup $full
  $text = ($Content -replace "`r`n", "`n").TrimEnd("`n") + "`n"
  [IO.File]::WriteAllText($full, $text, $global:CF_UTF8)
  Write-Host "WROTE  $Path" -ForegroundColor Green
}

function Patch-ProjectFile([string]$Path, [string]$Find, [string]$Replace, [string]$SkipIfContains) {
  $full = Join-Path $global:CF_ROOT $Path
  if (-not (Test-Path $full)) { Write-Host "MISSING $Path" -ForegroundColor Red; return }
  $t = [IO.File]::ReadAllText($full) -replace "`r`n", "`n"
  if ($SkipIfContains -and $t.Contains($SkipIfContains)) { Write-Host "ALREADY PATCHED $Path" -ForegroundColor Yellow; return }
  $idx = $t.IndexOf($Find)
  if ($idx -lt 0) { Write-Host "PATCH FAILED (text nahi mila) $Path" -ForegroundColor Red; return }
  CF-Backup $full
  $t = $t.Substring(0, $idx) + $Replace + $t.Substring($idx + $Find.Length)
  [IO.File]::WriteAllText($full, $t, $global:CF_UTF8)
  Write-Host "PATCHED $Path" -ForegroundColor Green
}

function Append-ProjectFile([string]$Path, [string]$Content, [string]$SkipIfContains) {
  $full = Join-Path $global:CF_ROOT $Path
  if (-not (Test-Path $full)) { Write-Host "MISSING $Path" -ForegroundColor Red; return }
  $t = [IO.File]::ReadAllText($full) -replace "`r`n", "`n"
  if ($SkipIfContains -and $t.Contains($SkipIfContains)) { Write-Host "ALREADY APPENDED $Path" -ForegroundColor Yellow; return }
  CF-Backup $full
  $t = $t.TrimEnd("`n") + "`n" + ($Content -replace "`r`n", "`n").TrimEnd("`n") + "`n"
  [IO.File]::WriteAllText($full, $t, $global:CF_UTF8)
  Write-Host "APPENDED $Path" -ForegroundColor Green
}