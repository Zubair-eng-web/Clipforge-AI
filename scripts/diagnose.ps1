# Needs the backend running (scripts\start-backend.ps1)
try {
  $d = Invoke-RestMethod http://localhost:8000/api/diagnostics
  $d | ConvertTo-Json -Depth 6
  if ($d.warnings.Count -gt 0) { Write-Host "`nWARNINGS:" -ForegroundColor Yellow; $d.warnings | ForEach-Object { Write-Host " - $_" -ForegroundColor Yellow } }
  else { Write-Host "`nAll checks OK." -ForegroundColor Green }
} catch { Write-Host "Backend is not running on http://localhost:8000" -ForegroundColor Red }