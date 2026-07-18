Write-Host "[Monitor] Waiting for all python backtest processes to finish..."
while ($true) {
    $procs = Get-Process python -ErrorAction SilentlyContinue
    if (-not $procs) {
        Write-Host "[Monitor] All python processes finished. Regenerating report..."
        Start-Sleep -Seconds 2
        Set-Location c:/fund
        python _generate_final_report.py 2>&1
        Write-Host "[Monitor] Report regenerated. Done."
        break
    }
    $count = $procs.Count
    $now = Get-Date -Format "HH:mm:ss"
    Write-Host "[Monitor] $now - $count python process(es) still running..."
    Start-Sleep -Seconds 120
}
