$root = Split-Path $PSScriptRoot
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "CLIPFORGE_AI.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = (Get-Command powershell.exe).Source
$s.Arguments = "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSScriptRoot\autostart.ps1`""
$s.WorkingDirectory = $root
$s.WindowStyle = 7
$s.Description = "CLIPFORGE AI autostart (servers + Edge)"
$s.Save()
Write-Host "Autostart ON: $lnk" -ForegroundColor Green
Write-Host "Band karne ke liye: .\scripts\disable-autostart.ps1"