$maxMinutes = 90
$pollSec = 120
$outfile = "C:\fund\v9-results\r5_poll.log"
$url = "https://raw.githubusercontent.com/wsxvg/ai-berkshire/master/v9-results/strict_oos_r5_eval.json"
$sw = [Diagnostics.Stopwatch]::StartNew()
"R5 poll started at $(Get-Date)" | Out-File $outfile

while ($sw.Elapsed.TotalMinutes -lt $maxMinutes) {
    Start-Sleep -Seconds $pollSec
    $elapsed = [int]$sw.Elapsed.TotalSeconds
    try {
        $req = [Net.WebRequest]::Create($url)
        $req.Headers.Add("Cache-Control", "no-cache")
        $resp = $req.GetResponse()
        $sr = New-Object IO.StreamReader($resp.GetResponseStream())
        $jsonText = $sr.ReadToEnd()
        $data = $jsonText | ConvertFrom-Json
        if ($data.summary) {
            "[{0}s] R5 FOUND!" -f $elapsed | Out-File $outfile -Append
            $data | ConvertTo-Json -Depth 10 | Out-File $outfile -Append
            $jsonText | Out-File "C:\fund\v9-results\strict_oos_r5_eval.json"
            "[{0}s] R5 SAVED." -f $elapsed | Out-File $outfile -Append
            exit 0
        }
    } catch {
        $err = $_.Exception.Message.Substring(0, [Math]::Min(120, $_.Exception.Message.Length))
        "[{0}s] waiting ({1})" -f $elapsed, $err | Out-File $outfile -Append
    }
}
"[{0}s] TIMEOUT" -f $elapsed | Out-File $outfile -Append
exit 1
