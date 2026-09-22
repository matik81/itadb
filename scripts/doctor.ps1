# Read-only inventory; does not install or alter system configuration.
$ErrorActionPreference = 'Continue'
$tools = @('git', 'gh', 'uv', 'node', 'npm.cmd', 'docker', 'psql', 'wsl')
foreach ($tool in $tools) {
    $found = Get-Command $tool -ErrorAction SilentlyContinue
    [PSCustomObject]@{ Tool = $tool; Available = [bool]$found; Path = $found.Source }
}
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture
Get-CimInstance Win32_ComputerSystem | Select-Object NumberOfLogicalProcessors, TotalPhysicalMemory
Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free
