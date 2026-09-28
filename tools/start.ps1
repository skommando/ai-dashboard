param(
    [string]$Runtime = (Join-Path $env:LOCALAPPDATA 'ai-dashboard\dev'),
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Runtime = [System.IO.Path]::GetFullPath($Runtime)
function Assert-ExternalPath([string]$Path, [string]$Label) {
    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full.Equals($repo, [System.StringComparison]::OrdinalIgnoreCase) -or
        $full.StartsWith($repo + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "[runtime_in_repo] $Label 必须在仓库之外。"
    }
    $part = $full
    while ($part) {
        if (Test-Path -LiteralPath $part) {
            $entry = Get-Item -LiteralPath $part -Force
            if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "$Label 不得经过符号链接或 junction。"
            }
        }
        $parent = [System.IO.Path]::GetDirectoryName($part)
        if (-not $parent -or $parent -eq $part) { break }
        $part = $parent
    }
}
Assert-ExternalPath $Runtime '运行目录'
if (Test-Path -LiteralPath $Runtime) {
    if (-not (Test-Path -LiteralPath $Runtime -PathType Container)) { throw '运行目录不是文件夹。' }
    $existing = @(Get-ChildItem -LiteralPath $Runtime -Force | Select-Object -First 1)
    $marker = Join-Path $Runtime '.dashboard-dev-runtime'
    if ($existing.Count -gt 0 -and
        (-not (Test-Path -LiteralPath $marker -PathType Leaf) -or
         (Get-Content -LiteralPath $marker -Raw).Trim() -ne 'ai-dashboard-dev-runtime-v1')) {
        throw '非空目录不是本工具的开发运行目录。'
    }
}
New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function Set-PrivateAcl([string]$Path, [bool]$Directory) {
    # Change only the DACL; a fresh descriptor can require SACL/owner privileges
    # on a previously protected directory in Windows PowerShell.
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($existingRule in @($acl.Access)) {
        $acl.RemoveAccessRuleSpecific($existingRule)
    }
    foreach ($identityValue in @($sid, 'S-1-5-18')) {
        $identity = [System.Security.Principal.SecurityIdentifier]::new($identityValue)
        if ($Directory) {
            $inheritance = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
                           [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
            $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
                $identity, [System.Security.AccessControl.FileSystemRights]::FullControl,
                $inheritance, [System.Security.AccessControl.PropagationFlags]::None,
                [System.Security.AccessControl.AccessControlType]::Allow)
        } else {
            $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
                $identity, [System.Security.AccessControl.FileSystemRights]::FullControl,
                [System.Security.AccessControl.AccessControlType]::Allow)
        }
        $acl.AddAccessRule($rule)
    }
    if ($Directory) { [System.IO.Directory]::SetAccessControl($Path, $acl) }
    else { [System.IO.File]::SetAccessControl($Path, $acl) }
}
Set-PrivateAcl $Runtime $true
foreach ($entry in @(Get-ChildItem -LiteralPath $Runtime -Force)) {
    Set-PrivateAcl $entry.FullName $entry.PSIsContainer
}
$marker = Join-Path $Runtime '.dashboard-dev-runtime'
if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
    Set-Content -LiteralPath $marker -Value 'ai-dashboard-dev-runtime-v1' -Encoding ascii
}
Set-PrivateAcl $marker $false
if (-not $Python) {
    $Python = Join-Path $Runtime 'venv\Scripts\python.exe'
    Assert-ExternalPath $Python 'Python 解释器'
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        & py -3.12 -m venv (Join-Path $Runtime 'venv')
        if ($LASTEXITCODE -ne 0) { throw '无法建立仓库外的 Python 3.12 venv。' }
        & $Python -m pip install --disable-pip-version-check -r (Join-Path $repo 'requirements-lock.txt')
        if ($LASTEXITCODE -ne 0) { throw '依赖安装失败。' }
    }
}
$Python = [System.IO.Path]::GetFullPath($Python)
Assert-ExternalPath $Python 'Python 解释器'
$pythonw = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
foreach ($file in @($Python, $pythonw, (Join-Path $repo 'scripts\service.py'), (Join-Path $repo 'scripts\start-dashboard.ps1'))) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "缺少必要文件：$file" }
}
& $Python -m pip check | Out-Null
if ($LASTEXITCODE -ne 0) { throw '开发环境依赖检查失败。' }

$config = Join-Path $Runtime 'service.json'
$old = $null
if (Test-Path -LiteralPath $config -PathType Leaf) {
    $old = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
    if ($old.runtime_directory -ne $Runtime) { throw '现有配置属于其他运行目录。' }
}
$user = if ($old) { [string]$old.environment.DASHBOARD_VIEW_USERNAME } else { $env:DASHBOARD_VIEW_USERNAME }
$password = if ($old) { [string]$old.environment.DASHBOARD_VIEW_PASSWORD } else { $env:DASHBOARD_VIEW_PASSWORD }
if (-not $user) { $user = Read-Host 'Basic Auth 用户名' }
if (-not $password) {
    $secure = Read-Host 'Basic Auth 密码' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
if (-not $user -or -not $password) { throw 'Basic Auth 用户名和密码不能为空。' }

$data = @{
    working_directory = $Runtime
    runtime_directory = $Runtime
    environment = @{
        PYTHONPATH = $repo
        DASHBOARD_DB_PATH = (Join-Path $Runtime 'dashboard.sqlite3')
        DASHBOARD_WEB_DIR = (Join-Path $repo 'web')
        DASHBOARD_VIEW_USERNAME = $user
        DASHBOARD_VIEW_PASSWORD = $password
    }
    components = @(@{
        name = 'app'
        command = @($Python, '-m', 'dashboard.server', '--host', '127.0.0.1', '--port', '8810')
    })
}
if ($old -and ($old.environment.PYTHONPATH -ne $repo -or $old.components[0].command[0] -ne $Python)) {
    $status = & $Python (Join-Path $repo 'scripts\service.py') status --config $config | ConvertFrom-Json
    if ($status.running) { throw '旧源码位置的服务仍在运行；请先停止。' }
}
$temporary = Join-Path $Runtime ('service-' + [guid]::NewGuid().ToString('N') + '.tmp')
try {
    $data | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $config -Force
    Set-PrivateAcl $config $false
} finally {
    Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue
}
& (Join-Path $repo 'scripts\start-dashboard.ps1') -Config $config -Python $Python -Pythonw $pythonw
if ($LASTEXITCODE -ne 0) { throw '本地服务启动失败。' }
$pair = [System.Text.Encoding]::UTF8.GetBytes($user + ':' + $password)
$authorization = 'Basic ' + [System.Convert]::ToBase64String($pair)
$healthy = $false
for ($attempt = 0; $attempt -lt 12; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8810/healthz' -Headers @{ Authorization = $authorization } -TimeoutSec 2 -UseBasicParsing
        if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch { Start-Sleep -Milliseconds 250 }
}
if (-not $healthy) {
    & (Join-Path $repo 'scripts\stop-dashboard.ps1') -Config $config -Python $Python | Out-Null
    throw '本地服务未通过健康检查。'
}
Write-Output '本地看板已在 127.0.0.1:8810 启动。'
