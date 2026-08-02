$maxAttempts = 240
$attempt = 0
while ($attempt -lt $maxAttempts) {
    $attempt++
    try {
        $resp = Invoke-WebRequest -Uri "https://raw.githubusercontent.com/wsxvg/ai-berkshire/master/v9-results/strict_oos_r6_eval.json" -UseBasicParsing -TimeoutSec 15
        if ($resp.StatusCode -eq 200) {
            $resp.Content | Out-File -FilePath "C:\fund\v9-results\strict_oos_r6_eval.json" -Encoding utf8
            Write-Output "SUCCESS: R6 results saved at attempt $attempt"
            exit 0
        }
    } catch {
        # 404 or network error
    }
    Write-Output "Attempt $attempt - waiting 30s..."
    Start-Sleep -Seconds 30
}
Write-Output "TIMEOUT after $maxAttempts attempts"
