param(
    [string]$Config = (Join-Path $PSScriptRoot '..\.runtime\service.json'),
    [string]$Python = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'),
    [string]$Pythonw = (Join-Path $PSScriptRoot '..\.venv\Scripts\pythonw.exe'),
    [string]$InstanceId = ''
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
if ($InstanceId -and $InstanceId -cnotmatch '^[0-9a-f]{32}$') {
    throw 'Invalid supervisor instance identity.'
}
$state = Get-DashboardState
$started = $null
if ($state.running) {
    if ($InstanceId -and $state.instance_id -cne $InstanceId) {
        throw 'Another supervisor instance is already running.'
    }
    $targetInstanceId = $state.instance_id
} else {
    $targetInstanceId = if ($InstanceId) { $InstanceId } else { [guid]::NewGuid().ToString('N') }
    $started = Start-Process -FilePath $Pythonw -ArgumentList @(
        "`"$Service`"", 'run', '--config', "`"$Config`"", '--instance-id', $targetInstanceId
    ) -WindowStyle Hidden -PassThru
}

try {
    $deadline = (Get-Date).AddSeconds(10)
    $healthySince = $null
    while ((Get-Date) -lt $deadline) {
        if ($null -ne $started) {
            $started.Refresh()
            if ($started.HasExited -and $started.ExitCode -ne 0) {
                throw "Dashboard launcher exited during startup (code $($started.ExitCode))."
            }
        }
        $state = Get-DashboardState
        if ($state.running -and $state.instance_id -cne $targetInstanceId) {
            throw 'Supervisor instance changed during startup.'
        }
        $ready = $state.running -and $state.instance_id -ceq $targetInstanceId
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
} catch {
    if ($null -ne $started) {
        $current = Get-DashboardState
        if ($current.running -and $current.instance_id -ceq $targetInstanceId) {
            & $Python $Service stop --config $Config --instance-id $targetInstanceId | Out-Null
        }
    }
    throw
}
