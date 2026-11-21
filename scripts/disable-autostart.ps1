$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "CLIPFORGE_AI.lnk"
if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "Autostart OFF (shortcut hata diya)" -ForegroundColor Yellow }
else { Write-Host "Autostart pehle se band hai" -ForegroundColor DarkGray }