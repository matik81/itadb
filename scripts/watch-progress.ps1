param([string]$LogPath = "$PSScriptRoot/../.tools/m2-progress.log")
$Host.UI.RawUI.WindowTitle = 'Itadb - avanzamento attivita'
Write-Host "Avanzamento e output delle operazioni: $LogPath"
Get-Content -LiteralPath $LogPath -Encoding UTF8 -Tail 30 -Wait
