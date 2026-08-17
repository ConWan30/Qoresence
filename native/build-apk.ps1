# Qoresence Glass — Android APK build script
# Usage: .\build-apk.ps1
# Requires: JDK 21 at C:\Users\Contr\jdk21\jdk-21.0.5+11
#           Android SDK at C:\Users\Contr\android-sdk

$env:JAVA_HOME = "C:\Users\Contr\jdk21\jdk-21.0.5+11"
$env:ANDROID_HOME = "C:\Users\Contr\android-sdk"
$env:PATH = "$env:JAVA_HOME\bin;$env:ANDROID_HOME\cmdline-tools\latest\bin;$env:ANDROID_HOME\platform-tools;$env:PATH"

Write-Host "Syncing Capacitor..." -ForegroundColor Cyan
Set-Location $PSScriptRoot
npx cap sync android

Write-Host "Building debug APK..." -ForegroundColor Cyan
Set-Location "$PSScriptRoot\android"
.\gradlew assembleDebug

$apk = "$PSScriptRoot\android\app\build\outputs\apk\debug\app-debug.apk"
if (Test-Path $apk) {
    $size = [math]::Round((Get-Item $apk).Length / 1MB, 2)
    Write-Host ""
    Write-Host "BUILD SUCCESSFUL" -ForegroundColor Green
    Write-Host "APK: $apk ($size MB)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Sideload to phone:" -ForegroundColor Cyan
    Write-Host "  1. Copy app-debug.apk to your phone (USB, Drive, etc.)"
    Write-Host "  2. Open it on the phone (enable 'Install unknown apps' if prompted)"
    Write-Host "  3. Open Qoresence Glass — it will auto-discover your PC on Wi-Fi"
} else {
    Write-Host "BUILD FAILED — APK not found" -ForegroundColor Red
    exit 1
}
