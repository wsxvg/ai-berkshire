 = 240  # 240 attempts × 30s = 2 hours
 = 0
while ( -lt ) {
    ++
    try {
         = Invoke-WebRequest -Uri "https://raw.githubusercontent.com/wsxvg/ai-berkshire/master/v9-results/strict_oos_r6_eval.json" -UseBasicParsing -TimeoutSec 15
        if (.StatusCode -eq 200) {
            .Content | Out-File -FilePath "C:\fund\v9-results\strict_oos_r6_eval.json" -Encoding utf8
            Write-Output "SUCCESS: R6 results saved at attempt "
            exit 0
        }
    } catch {
        # 404 or network error, keep polling
    }
    Write-Output "Attempt  - not available yet, waiting 30s..."
    Start-Sleep -Seconds 30
}
Write-Output "TIMEOUT: Results not available after  attempts"
