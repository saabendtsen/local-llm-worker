@echo off
setlocal

rem Confirm the local worker runtime is up and can complete a chat request.

if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=8000"
rem Floor for the resident set once the weights are locked. ~17 GB is the
rem expected figure for Q4_K_M at NCMOE=38; 12 leaves room for a smaller
rem quant or a future NCMOE change without making this check a tripwire.
if not defined MIN_LOCKED_GB set "MIN_LOCKED_GB=12"

set "BASE=http://%HOST%:%PORT%"

echo == health ==
rem -f matters: without it curl exits 0 for ANY completed exchange, including the
rem 503 the server returns while the model is still loading. A health check that
rem passes 47 seconds early sends every request into a server that is not there
rem yet, and the run looks like a model that refused to act.
curl.exe -sf --max-time 10 "%BASE%/health"
if errorlevel 1 (
    echo.
    echo ERROR: %BASE% is not ready. Either start-worker.cmd is not running,
    echo or the model is still loading ^(that takes 20-55 seconds^).
    exit /b 1
)
echo.

echo.
echo == locked memory ==
rem mlock is not guaranteed. VirtualLock is bounded by the process working-set
rem quota, so a runtime started on an already-contended machine warns once and
rem then serves with pageable weights. Nothing else in this script notices:
rem health returns 200 and a short completion still comes back. But the expert
rem tensors then fault off the SSD per token and generation collapses from
rem ~25 tok/s to under 1, which reads as a hung or stupid model rather than as
rem the environment fault it is. Same family as the 503 above: assert the
rem condition, never infer it from a request that happened to succeed.
powershell.exe -NoProfile -Command "$p = Get-Process llama-server -ErrorAction SilentlyContinue | Sort-Object WorkingSet64 -Descending | Select-Object -First 1; if (-not $p) { Write-Host 'SKIP: no llama-server process here; cannot verify locked memory for a remote endpoint.'; exit 0 }; $gb = [math]::Round($p.WorkingSet64/1GB,1); if ($gb -lt %MIN_LOCKED_GB%) { Write-Host ('ERROR: llama-server resident set is {0} GB, below the {1} GB floor. mlock most likely did not take, so generation will be disk-bound. Free RAM and restart start-worker.cmd rather than scoring any run from this runtime.' -f $gb, %MIN_LOCKED_GB%); exit 1 }; Write-Host ('resident set {0} GB, weights are locked' -f $gb)"
if errorlevel 1 exit /b 1

echo.
echo == models ==
curl.exe -s --max-time 10 "%BASE%/v1/models"
echo.

echo.
echo == completion ==
rem max_tokens must be generous: this is a reasoning model, and the thinking trace is
rem spent from the same budget. A small limit returns an empty `content` with a full
rem token count, which looks like a broken server but is only a truncated thought.
curl.exe -s --max-time 300 "%BASE%/v1/chat/completions" ^
    -H "Content-Type: application/json" ^
    -d "{\"model\":\"local-worker\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: worker ready\"}],\"max_tokens\":512}"
echo.

endlocal
