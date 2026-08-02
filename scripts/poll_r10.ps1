$repo = "wsxvg/ai-berkshire"
$targetSha = "81ebeed39baa6ffaac732025e5b025226d15085f"
$pollInterval = 120  # seconds
$maxPolls = 60  # 2 hours max

for ($i = 1; $i -le $maxPolls; $i++) {
    Start-Sleep -Seconds $pollInterval
    try {
        $runs = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/actions/runs?per_page=5" -TimeoutSec 30
        $targetRuns = $runs.workflow_runs | Where-Object { $_.head_sha -eq $targetSha }
        if (-not $targetRuns) {
            Write-Host "[$i] No runs found for $targetSha yet..."
            continue
        }
        $running = ($targetRuns | Where-Object { $_.status -ne "completed" }).Count
        $completed = ($targetRuns | Where-Object { $_.status -eq "completed" }).Count
        $total = $targetRuns.Count
        $success = ($targetRuns | Where-Object { $_.conclusion -eq "success" }).Count
        $failed = ($targetRuns | Where_Object { $_.conclusion -eq "failure" }).Count
        Write-Host "[$i] Poll: $completed/$total completed (running=$running, success=$success, failed=$failed)"
        
        if ($running -eq 0 -and $completed -gt 0) {
            Write-Host "ALL DONE! success=$success failed=$failed"
            break
        }
    } catch {
        Write-Host "[$i] Error: $_"
    }
}
