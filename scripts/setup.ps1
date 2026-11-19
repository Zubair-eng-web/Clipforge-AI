Set-Location (Split-Path $PSScriptRoot)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host "Backend setup complete." -ForegroundColor Green