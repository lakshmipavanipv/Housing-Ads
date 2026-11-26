# Flashes the Ring QA bridge firmware onto every ESP32 board plugged into this laptop.
# Run by double-clicking flash_bridges.bat. Needs internet the first time (downloads ~500 MB of ESP32 tools).
param(
  [string]$Fqbn = "",
  [string[]]$Ports = @()
)
$ErrorActionPreference = "Stop"
$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$tools = Join-Path $here "tools"
$cli   = Join-Path $tools "arduino-cli.exe"
$url   = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"
New-Item -ItemType Directory -Force $tools | Out-Null

function Run([string[]]$cliArgs) {
  & $cli @cliArgs
  if ($LASTEXITCODE -ne 0) { throw "arduino-cli $($cliArgs -join ' ') failed" }
}

if (-not (Test-Path $cli)) {
  Write-Host "Downloading arduino-cli..." -ForegroundColor Cyan
  $zip = Join-Path $tools "arduino-cli.zip"
  Invoke-WebRequest "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip" -OutFile $zip
  Expand-Archive $zip -DestinationPath $tools -Force
  Remove-Item $zip
}

Write-Host "Installing ESP32 board support and the NimBLE library (first time only, takes a few minutes)..." -ForegroundColor Cyan
Run @("core", "update-index", "--additional-urls", $url)
Run @("core", "install", "esp32:esp32@2.0.17", "--additional-urls", $url)
Run @("lib", "install", "NimBLE-Arduino@1.4.3")

if (-not $Fqbn) {
  Write-Host ""
  Write-Host "Which ESP32 boards do you have?"
  Write-Host "  1) ESP32 (classic: ESP32-WROOM / ESP32 DevKit)  [default]"
  Write-Host "  2) ESP32-S3"
  Write-Host "  3) ESP32-C3"
  $c = Read-Host "Enter 1, 2 or 3"
  $Fqbn = @{ "2" = "esp32:esp32:esp32s3"; "3" = "esp32:esp32:esp32c3" }[$c]
  if (-not $Fqbn) { $Fqbn = "esp32:esp32:esp32" }
}

$sketch = Join-Path $here "firmware\rqa_bridge"
$build  = Join-Path $tools "build"
Write-Host "Compiling firmware for $Fqbn ..." -ForegroundColor Cyan
Run @("compile", "--fqbn", $Fqbn, "--build-path", $build,
      "--build-property", "compiler.cpp.extra_flags=-DCONFIG_BT_NIMBLE_MAX_CONNECTIONS=9",
      "--build-property", "compiler.c.extra_flags=-DCONFIG_BT_NIMBLE_MAX_CONNECTIONS=9", $sketch)

if (-not $Ports) {
  $Ports = Get-CimInstance Win32_PnPEntity |
    Where-Object { $_.Name -match '\(COM\d+\)' -and $_.Name -match 'CP210|CH340|CH910|CH9102|USB-SERIAL|USB Serial|USB JTAG|FTDI' } |
    ForEach-Object { [regex]::Match($_.Name, 'COM\d+').Value } | Sort-Object -Unique
}
if (-not $Ports) { throw "No ESP32 COM ports found. Check Device Manager > Ports (COM & LPT) and the USB hub power." }

Write-Host ""
Write-Host "ESP32 boards found on: $($Ports -join ', ')" -ForegroundColor Yellow
$ok = Read-Host "Flash the bridge firmware to ALL of these ports? (Y/N)"
if ($ok -notmatch '^[Yy]') { Write-Host "Cancelled."; exit 1 }

$failed = @()
foreach ($p in $Ports) {
  Write-Host "Flashing $p ..." -ForegroundColor Cyan
  & $cli upload -p $p --fqbn $Fqbn --input-dir $build $sketch
  if ($LASTEXITCODE -ne 0) { $failed += $p }
}
Write-Host ""
if ($failed) {
  Write-Host "FAILED on: $($failed -join ', ')" -ForegroundColor Red
  Write-Host "Hold the BOOT button on that board, then run:  flash_bridges.bat -Ports $($failed[0])"
} else {
  Write-Host "All boards flashed. Now double-click start_portal.bat" -ForegroundColor Green
}
