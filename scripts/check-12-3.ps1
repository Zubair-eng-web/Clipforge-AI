$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$fail = 0
function Ok($m)  { Write-Host "PASS  $m" -ForegroundColor Green }
function Bad($m) { Write-Host "FAIL  $m" -ForegroundColor Red; $script:fail++ }

if (Test-Path "frontend/app/gaming-highlights/page.tsx") { Ok "page file exists" } else { Bad "page file missing" }
if ((Get-Content "frontend/lib/nav.ts" -Raw) -match "gaming-highlights") { Ok "sidebar link present" } else { Bad "sidebar link missing" }

try {
  $c = Invoke-RestMethod "http://localhost:8000/api/gaming/categories"
  if ($c.items.Count -ge 26) { Ok "gaming categories: $($c.items.Count)" } else { Bad "categories count $($c.items.Count)" }
} catch { Bad "backend not running (.\scripts\start-backend.ps1)" }

try {
  $v = Invoke-RestMethod "http://localhost:8000/api/videos?limit=5"
  if ($v.items.Count -gt 0) {
    $id = $v.items[0].id
    $h = Invoke-RestMethod "http://localhost:8000/api/gaming/videos/$id/highlights"
    Ok "highlights endpoint works (video $id, $($h.items.Count) items)"
  } else { Write-Host "SKIP  no uploaded video for endpoint test" -ForegroundColor Yellow }
} catch { Bad "highlights endpoint error" }

Write-Host "Running TypeScript check (1-2 min)..." -ForegroundColor Cyan
Push-Location frontend
npx tsc --noEmit
if ($LASTEXITCODE -eq 0) { Ok "TypeScript: no errors" } else { Bad "TypeScript errors above" }
Pop-Location

Write-Host "Running backend tests..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m pytest -q
if ($LASTEXITCODE -eq 0) { Ok "pytest passed" } else { Bad "pytest failed" }

if ($fail -eq 0) { Write-Host "`nALL GOOD. Open http://localhost:3000/gaming-highlights and test by hand." -ForegroundColor Green }
else { Write-Host "`n$fail check(s) failed. Paste the output in chat." -ForegroundColor Red }