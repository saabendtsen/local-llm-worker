# Windows Firewall state for LAN mode (homelab-workspace#360). Run elevated.
#
#   -Status  show the rules that decide whether the server reaches the model (no elevation needed)
#   -Apply   allow TCP 8000 from the homelab server only, and disable every program-level
#            Block rule for llama-server.exe
#   -Remove  delete the allow rule and re-enable those Block rules
#
# Why the Block rules: Windows creates inbound Block rules named "llama-server" or
# "llama-server.exe" when its first-run prompt is dismissed. The dev PC's Ethernet
# profile is Public, those rules cover Public, and Block always beats Allow -- which
# silently broke the #338 spike twice.
param(
    [switch]$Status,
    [switch]$Apply,
    [switch]$Remove,
    [string]$ServerAddress = '192.168.0.100',
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$allowName = 'local-worker LAN (from home-server)'
$legacyAllowNames = @('llama-server LAN test (from home-server)')

function Get-ProgramBlockRules {
    Get-NetFirewallRule -Direction Inbound -Action Block -ErrorAction SilentlyContinue |
        Where-Object {
            $_.DisplayName -in @('llama-server', 'llama-server.exe') -or
            (($_ | Get-NetFirewallApplicationFilter).Program -like '*\llama-server.exe')
        }
}

if (-not ($Status -or $Apply -or $Remove)) { $Status = $true }
if (($Apply -or $Remove) -and -not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run elevated to change firewall rules.'
}

if ($Apply) {
    foreach ($legacy in $legacyAllowNames) { Remove-NetFirewallRule -DisplayName $legacy -ErrorAction SilentlyContinue }
    Remove-NetFirewallRule -DisplayName $allowName -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $allowName -Direction Inbound -Protocol TCP -LocalPort $Port `
        -RemoteAddress $ServerAddress -Action Allow -Profile Any | Out-Null
    Get-ProgramBlockRules | Disable-NetFirewallRule
}
if ($Remove) {
    Remove-NetFirewallRule -DisplayName $allowName -ErrorAction SilentlyContinue
    Get-ProgramBlockRules | Enable-NetFirewallRule
}

Get-NetConnectionProfile | Select-Object InterfaceAlias, NetworkCategory | Format-Table -AutoSize
Get-NetFirewallRule -Direction Inbound -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -eq $allowName -or $_.DisplayName -in @('llama-server', 'llama-server.exe') -or $_.DisplayName -in $legacyAllowNames } |
    Select-Object DisplayName, Enabled, Action, Profile | Format-Table -AutoSize
