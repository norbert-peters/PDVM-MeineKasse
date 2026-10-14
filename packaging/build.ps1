<#
.SYNOPSIS
    Baut das Installationspaket (Ordner + ZIP) von Meine Kasse mit PyInstaller.

.DESCRIPTION
    Voraussetzung: virtuelle Umgebung .venv mit installierten Paketen
    (pip install -e ".[dev,build]"). Ergebnis:
      dist\MeineKasse\            - lauffähiger Ordner (MeineKasse.exe)
      dist\MeineKasse-<Version>-win64.zip
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Die virtuelle Umgebung .venv wurde nicht gefunden." }

$version = & $python -c "import meine_kasse; print(meine_kasse.__version__)"
$buildStart = Get-Date
Write-Host "Baue Meine Kasse $version (Beginn $($buildStart.ToString('dd.MM.yyyy HH:mm:ss'))) ..."

# Der Zeitpunkt des Builds-Beginns wird als Datei ins Paket gegeben und in
# Hilfe > Über Meine Kasse angezeigt. Die Datei gehört nicht in die Versionsverwaltung.
$buildInfo = Join-Path $root "src\meine_kasse\_build_info.py"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $buildInfo,
    "BUILD_TIMESTAMP = `"$($buildStart.ToString('yyyy-MM-ddTHH:mm:ss', [cultureinfo]::InvariantCulture))`"`n",
    $utf8
)

try {
    Remove-Item -Recurse -Force "build", "dist" -ErrorAction SilentlyContinue
    Get-ChildItem -Path "src" -Recurse -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    & $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build "packaging\meine_kasse.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller ist fehlgeschlagen." }
} finally {
    Remove-Item $buildInfo -Force -ErrorAction SilentlyContinue
}

& (Join-Path $PSScriptRoot "smoke_test.ps1") -Folder "dist\MeineKasse"

Copy-Item "packaging\LIESMICH.txt" "dist\MeineKasse\LIESMICH.txt"

$zip = "dist\MeineKasse-$version-win64.zip"
Compress-Archive -Path "dist\MeineKasse" -DestinationPath $zip -Force
Write-Host "Fertig: $zip"
