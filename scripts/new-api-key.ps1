# Creates the llama-server API key used in LAN mode (homelab-workspace#360), if absent.
# The key lives outside the repository, readable by the current user only, and is
# never printed. Hand it to the server lane with:
#   gh secret set LOCAL_WORKER_API_KEY --repo Wibholm-solutions/sandcastle-wayfinder-pilot < "$env:USERPROFILE\.local-worker\api-key"
param([string]$Path = (Join-Path $env:USERPROFILE '.local-worker\api-key'))
$ErrorActionPreference = 'Stop'

if (Test-Path -LiteralPath $Path) {
    Write-Output "API key already exists at $Path; leaving it unchanged."
    exit 0
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$key = -join ($bytes | ForEach-Object { $_.ToString('x2') })
[System.IO.File]::WriteAllText($Path, $key, (New-Object System.Text.UTF8Encoding $false))

# Owner-only: drop inherited ACEs, grant the current user full control.
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true, $false)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($user, 'FullControl', 'Allow')))
Set-Acl -LiteralPath $Path -AclObject $acl
Write-Output "Created API key at $Path (owner-only)."
