@echo off
rem Serve the model to the homelab server's agent-local runner lane over the wired LAN
rem (homelab-workspace#334, #360). Binds the dev PC's LAN address only -- never
rem 0.0.0.0, so the endpoint stays off Tailscale -- and requires the API key.
rem Pair with scripts\lan-firewall.ps1 -Apply (elevated). See docs\runtime.md "LAN mode".
setlocal
if not defined LAN_HOST set "LAN_HOST=192.168.0.204"
set "HOST=%LAN_HOST%"
call "%~dp0start-worker.cmd"
endlocal
