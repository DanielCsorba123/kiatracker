<#
.SYNOPSIS
    Nightly backup of the collector's raw data (the irreplaceable part) from the Pi to this PC.

.DESCRIPTION
    Packs data/raw on the collector host into a tar.gz, copies it here with scp (byte-safe), checks the
    archive opens and holds the raw files, and keeps the newest -KeepDaily nights plus the first backup of
    every month. Retries a few times, since the Pi is often on Wi-Fi. Everything else in data/ (database,
    model, terrain tiles) is rebuilt from raw: restore = extract into data/ and run `kiatracker build`.

    Schedule it with Task Scheduler (daily, "run as soon as possible after a missed start"), e.g.:
      powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\backup-pi.ps1 -Target you@pi -Key ~\.ssh\id

.EXAMPLE
    .\scripts\backup-pi.ps1 -Target daniel@my-pi -Key $HOME\.ssh\pi_ed25519
#>
param(
    [Parameter(Mandatory)] [string] $Target,          # user@host of the collector (e.g. its Tailscale name)
    [Parameter(Mandatory)] [string] $Key,             # SSH private key with access to that host
    [string] $RemoteData = "kiatracker/data",         # data folder on the host, relative to the home folder
    [string] $Destination = "D:\kiatracker-backups",  # where archives are kept on this PC
    [int] $KeepDaily = 30,
    [int] $Attempts = 6
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $Destination | Out-Null
$log = Join-Path $Destination "backup.log"
function Log($message) {
    $line = "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $message
    Add-Content -Path $log -Value $line -Encoding utf8
    Write-Output $line
}

$stamp = Get-Date -Format "yyyy-MM-dd"
$final = Join-Path $Destination "raw-$stamp.tar.gz"
$partial = "$final.partial"
$remote = "/tmp/kiatracker-raw-backup.tar.gz"
$ssh = @("-i", $Key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=15")

for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    try {
        & ssh @ssh $Target "tar czf $remote -C $RemoteData raw && ls -l $remote" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "packing on the host failed (exit $LASTEXITCODE)" }
        & scp @ssh -q "${Target}:$remote" $partial
        if ($LASTEXITCODE -ne 0) { throw "copy failed (exit $LASTEXITCODE)" }
        & ssh @ssh $Target "rm -f $remote" | Out-Null

        $files = & tar -tzf $partial
        if ($LASTEXITCODE -ne 0) { throw "archive does not open" }
        $snapshots = @($files | Where-Object { $_ -match "^raw/snapshots-\d{4}-\d{2}\.jsonl$" })
        if ($snapshots.Count -eq 0) { throw "archive holds no snapshot files" }

        Move-Item -Force $partial $final
        $size = [math]::Round((Get-Item $final).Length / 1KB)
        Log "OK  $final  ($size KB, $($files.Count) entries, $($snapshots.Count) snapshot months, attempt $attempt)"
        break
    }
    catch {
        Remove-Item -Force -ErrorAction SilentlyContinue $partial
        Log "attempt $attempt failed: $($_.Exception.Message)"
        if ($attempt -eq $Attempts) { Log "FAILED: no backup tonight"; exit 1 }
        Start-Sleep -Seconds 120
    }
}

# Keep the newest nights, plus the first backup of each month for the long run.
$archives = Get-ChildItem $Destination -Filter "raw-*.tar.gz" | Sort-Object Name -Descending
$monthly = $archives | Group-Object { $_.Name.Substring(4, 7) } | ForEach-Object {
    ($_.Group | Sort-Object Name | Select-Object -First 1).Name
}
$archives | Select-Object -Skip $KeepDaily | Where-Object { $monthly -notcontains $_.Name } | ForEach-Object {
    Remove-Item -Force $_.FullName
    Log "pruned $($_.Name)"
}
exit 0
