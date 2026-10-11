<#
.SYNOPSIS
    Startet das gebaute Paket ohne Oberfläche (offscreen) gegen eine frische Datenbank und prüft,
    dass die Migration lief und kein Fehler protokolliert wurde.

.PARAMETER Folder
    Ordner mit MeineKasse.exe (Standard: dist\MeineKasse).
#>
param([string]$Folder = "dist\MeineKasse")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
$exe = Join-Path (Resolve-Path $Folder) "MeineKasse.exe"
if (-not (Test-Path $exe)) { throw "MeineKasse.exe nicht gefunden: $exe" }

$work = Join-Path $env:TEMP ("MeineKasse_smoke_" + [guid]::NewGuid().ToString("N"))
$db = Join-Path $work "kasse.sqlite"
$log = Join-Path $work "logs\meine_kasse.log"
$env:MEINE_KASSE_DB = $db
$env:QT_QPA_PLATFORM = "offscreen"
$checkScript = @'
import sqlite3, sys
try:
    rows = sqlite3.connect(sys.argv[1]).execute("select version_num from alembic_version").fetchall()
    print(rows[0][0] if rows else "")
except sqlite3.Error:
    print("")
'@

$problems = @()

# 1. Selbsttest: Argon2, Migrationen, Buchen, Abschluss, Sicherung in einer temporären Datenbank
$selftest = Start-Process -FilePath $exe -ArgumentList "--selbsttest" -PassThru -WindowStyle Hidden
if (-not $selftest.WaitForExit(300000)) {
    Stop-Process -Id $selftest.Id -Force
    $problems += "Der Selbsttest wurde nicht rechtzeitig beendet."
} elseif ($selftest.ExitCode -ne 0) {
    $problems += "Der Selbsttest ist fehlgeschlagen (Exitcode $($selftest.ExitCode))."
}

# 2. Oberfläche startet und migriert die Datenbank
$process = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
$version = ""
try {
    $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline -and -not $process.HasExited -and -not $version) {
        Start-Sleep -Seconds 1
        if (Test-Path $db) { $version = ($checkScript | & $python - $db).Trim() }
    }
    Start-Sleep -Seconds 2
    $crashed = $process.HasExited
} finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    Start-Sleep -Seconds 1
}

if (-not $version) { $problems += "Die Datenbank wurde nicht migriert." }
if ($crashed) { $problems += "Das Programm hat sich vorzeitig beendet." }
if (Test-Path $log) {
    $errors = Select-String -Path $log -Pattern " (ERROR|CRITICAL) " -Encoding UTF8
    if ($errors) { $problems += "Im Protokoll stehen Fehler:`n" + (Get-Content $log -Encoding UTF8 -TotalCount 25 | Out-String) }
} else {
    $problems += "Es wurde keine Protokolldatei angelegt."
}
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
if ($problems) { throw ("Smoke-Test fehlgeschlagen:`n" + ($problems -join "`n")) }
Write-Host "Smoke-Test bestanden (Datenbankversion $version)."
