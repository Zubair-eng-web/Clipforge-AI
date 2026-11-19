$root = Split-Path $PSScriptRoot
New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null

$b = Start-Process powershell -PassThru -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-File","`"$PSScriptRoot\start-backend.ps1`"")
$f = Start-Process powershell -PassThru -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-File","`"$PSScriptRoot\start-frontend.ps1`"")
"$($b.Id)`n$($f.Id)" | Set-Content (Join-Path $root "logs\pids.txt")

Write-Host "Starting... browser 8 seconds mein khulega." -ForegroundColor Cyan
Start-Sleep -Seconds 8
Start-Process "http://localhost:3000"