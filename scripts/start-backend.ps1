Set-Location (Split-Path $PSScriptRoot)
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --reload-dir backend --port 8000