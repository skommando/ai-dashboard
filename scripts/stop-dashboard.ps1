param(
    [string]$Config = (Join-Path $PSScriptRoot '..\.runtime\service.json'),
    [string]$Python = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe')
)

$ErrorActionPreference = 'Stop'
$Config = [System.IO.Path]::GetFullPath($Config)
$Python = [System.IO.Path]::GetFullPath($Python)
$Service = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'service.py'))

& $Python $Service stop --config $Config
if ($LASTEXITCODE -ne 0) { throw 'Dashboard supervisor stop failed.' }
