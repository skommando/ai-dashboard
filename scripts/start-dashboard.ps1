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

function Get-DashboardState {
    $stateText = & $Python $Service status --config $Config
    if ($LASTEXITCODE -ne 0) { throw 'Dashboard status check failed; check the local configuration.' }
    return ($stateText | ConvertFrom-Json)
}

$configData = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$expectedNames = @($configData.components | ForEach-Object { $_.name })
if ($expectedNames.Count -eq 0) { throw 'Dashboard has no configured components.' }
$state = Get-DashboardState
$started = $null
if (-not $state.running) {
    $started = Start-Process -FilePath $Pythonw -ArgumentList @("`"$Service`"", 'run', '--config', "`"$Config`"") -WindowStyle Hidden -PassThru
}

$deadline = (Get-Date).AddSeconds(10)
$healthySince = $null
while ((Get-Date) -lt $deadline) {
    if ($null -ne $started) {
        $started.Refresh()
        if ($started.HasExited) { throw "Dashboard supervisor exited during startup (code $($started.ExitCode))." }
    }
    $state = Get-DashboardState
    $ready = $state.running
    if ($ready -and $null -ne $started) { $ready = ($state.pid -eq $started.Id) }
    if ($ready) {
        foreach ($name in $expectedNames) {
            $component = @($state.components | Where-Object { $_.name -eq $name })
            if ($component.Count -ne 1 -or -not $component[0].pid) {
                $ready = $false
                break
            }
        }
    }
    if ($ready) {
        if ($null -eq $healthySince) { $healthySince = Get-Date }
        if (((Get-Date) - $healthySince).TotalSeconds -ge 1) {
            Write-Output "Dashboard supervisor and $($expectedNames.Count) components are running."
            exit 0
        }
    } else {
        $healthySince = $null
    }
    Start-Sleep -Milliseconds 200
}

if ($null -ne $started -and $state.running -and $state.pid -eq $started.Id) {
    & $Python $Service stop --config $Config | Out-Null
}
$pending = @($expectedNames | ForEach-Object {
    $name = $_
    $component = @($state.components | Where-Object { $_.name -eq $name })
    if ($component.Count -ne 1 -or -not $component[0].pid) {
        if ($component.Count -eq 1 -and $component[0].last_error) {
            "${name}($($component[0].last_error))"
        } elseif ($component.Count -eq 1 -and $null -ne $component[0].last_exit_code) {
            "${name}(exit $($component[0].last_exit_code))"
        } else {
            $name
        }
    }
})
throw "Dashboard startup timed out; unavailable components: $($pending -join ', ')."
