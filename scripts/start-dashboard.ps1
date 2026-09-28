param(
    [string]$Config = (Join-Path $PSScriptRoot '..\.runtime\service.json'),
    [string]$Python = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'),
    [string]$Pythonw = (Join-Path $PSScriptRoot '..\.venv\Scripts\pythonw.exe')
)

$ErrorActionPreference = 'Stop'
$Config = [System.IO.Path]::GetFullPath($Config)
$Python = [System.IO.Path]::GetFullPath($Python)
$Pythonw = [System.IO.Path]::GetFullPath($Pythonw)
$Service = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'service.py'))

foreach ($file in @($Config, $Python, $Pythonw, $Service)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Missing required file: $file"
    }
}

$stateText = & $Python $Service status --config $Config
if ($LASTEXITCODE -ne 0) { throw 'Dashboard status check failed.' }
$state = $stateText | ConvertFrom-Json
if ($state.running) {
    Write-Output "Dashboard supervisor is already running (PID $($state.pid))."
    exit 0
}

Start-Process -FilePath $Pythonw -ArgumentList @("`"$Service`"", 'run', '--config', "`"$Config`"") -WindowStyle Hidden
Write-Output 'Dashboard supervisor start requested.'
