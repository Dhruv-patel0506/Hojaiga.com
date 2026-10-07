$ErrorActionPreference = "SilentlyContinue"
Start-Sleep -Seconds 30
try {
    $h = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8081/health").Content
    Write-Host "HEALTH: $h"
} catch {
    Write-Host "HEALTH-ERR: $($_.Exception.Message)"
}
try {
    $p = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8081/props").Content | ConvertFrom-Json
    Write-Host "MODEL: $($p.model_path)"
    Write-Host "MMPROJ: $($p.mmproj_path)"
    Write-Host "TIMING: n_tokens=$($p.timings.tokens_per_second)"
} catch {
    Write-Host "PROPS-ERR: $($_.Exception.Message)"
}
