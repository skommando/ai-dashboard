param(
    [string]$Runtime = (Join-Path $env:LOCALAPPDATA 'ai-dashboard\dev'),
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Runtime = [System.IO.Path]::GetFullPath($Runtime)
if ($Runtime.Equals($repo, [System.StringComparison]::OrdinalIgnoreCase) -or
    $Runtime.StartsWith($repo + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw '运行目录必须在仓库之外。'
}
$part = $Runtime
while ($part) {
    if (Test-Path -LiteralPath $part) {
        $entry = Get-Item -LiteralPath $part -Force
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw '运行目录不得经过符号链接或 junction。'
        }
    }
    $parent = [System.IO.Path]::GetDirectoryName($part)
    if (-not $parent -or $parent -eq $part) { break }
    $part = $parent
}
$config = Join-Path $Runtime 'service.json'
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) { throw '找不到本地服务配置。' }
if (-not $Python) {
    $saved = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
    $Python = [string]$saved.components[0].command[0]
}
& (Join-Path $repo 'scripts\stop-dashboard.ps1') -Config $config -Python $Python
if ($LASTEXITCODE -ne 0) { throw '本地服务停止失败。' }
