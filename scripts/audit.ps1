$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "=== AUDIT ===" -ForegroundColor Cyan
.\.venv\Scripts\python.exe scripts\audit_project.py
Write-Host "Done. Report: AUDIT_REPORT.md" -ForegroundColor Green
