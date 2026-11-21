Set-Location (Split-Path $PSScriptRoot)
function Check($name, $ok, $hint) {
  if ($ok) { Write-Host "[OK]   $name" -ForegroundColor Green }
  else { Write-Host "[FAIL] $name  ->  $hint" -ForegroundColor Red }
}
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

Check "Python venv"        (Test-Path ".\.venv\Scripts\python.exe") "Run .\scripts\setup.ps1"
Check "Node.js"            (Has "node")   "Install Node 20+ from nodejs.org"
Check "FFmpeg"             (Has "ffmpeg") "winget install Gyan.FFmpeg (phir VS Code restart)"
Check "FFprobe"            (Has "ffprobe") "FFmpeg ke saath aata hai"
Check "Frontend packages"  (Test-Path "frontend\node_modules") "cd frontend; npm install"
Check ".env file"          (Test-Path ".env") "Copy .env.example to .env"

$envText = if (Test-Path ".env") { Get-Content ".env" -Raw } else { "" }
Check "Gemini API key set (.env or Gemini Key page)" ((Test-Path "storage\settings\gemini_key.json") -or ($envText -match "GEMINI_API_KEY=(?!your_key_here)\S+")) "Gemini API Key page ya .env mein key daalo"

foreach ($port in 8000, 3000) {
  $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if ($busy) { Write-Host "[INFO] Port $port in use (app chal raha hai ya koi aur program)" -ForegroundColor Yellow }
  else { Write-Host "[OK]   Port $port free" -ForegroundColor Green }
}