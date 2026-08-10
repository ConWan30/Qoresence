[CmdletBinding()]
param(
    [string]$OutputDirectory = "dist",
    [string]$Version = "dev"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$output = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
}
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("qoresence-package-" + [guid]::NewGuid().ToString("N"))
$payload = Join-Path $stage "Qoresence"
$version = if ([string]::IsNullOrWhiteSpace($Version)) { "dev" } else { $Version.Trim() }

New-Item -ItemType Directory -Path $payload -Force | Out-Null
New-Item -ItemType Directory -Path $output -Force | Out-Null

$directories = @(
    "qoresence",
    "docs",
    "examples",
    "profiles",
    "scripts",
    "tests"
)
$files = @(
    "AGENTS.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "PRIVACY.md",
    "README.md",
    "SECURITY.md",
    "pyproject.toml",
    "qoresence.bat"
)

foreach ($relative in $directories) {
    $source = Join-Path $repoRoot $relative
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination $payload -Recurse -Force
    }
}
foreach ($relative in $files) {
    $source = Join-Path $repoRoot $relative
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination $payload -Force
    }
}

$installerRoot = Join-Path $repoRoot "installer\windows"
Copy-Item (Join-Path $installerRoot "Install-Qoresence.ps1") (Join-Path $payload "Install-Qoresence.ps1") -Force
Copy-Item (Join-Path $installerRoot "Start-Qoresence.bat") (Join-Path $payload "Start-Qoresence.bat") -Force

$manifest = [ordered]@{
    product = "Qoresence"
    package = "Windows starter package"
    version = $version
    created_utc = (Get-Date).ToUniversalTime().ToString("o")
    python = "3.11+"
    install = "Install-Qoresence.ps1"
    launch = "Start-Qoresence.bat"
    local_only_by_default = $true
    notes = "Capture hardware and vendor drivers are not bundled."
}
$manifest | ConvertTo-Json | Set-Content (Join-Path $payload "package-manifest.json") -Encoding utf8

$zip = Join-Path $output "Qoresence-Windows.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $payload -DestinationPath $zip -CompressionLevel Optimal -Force
$hash = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -Path "$zip.sha256" -Value "$hash  Qoresence-Windows.zip" -Encoding ascii

Write-Host "Package: $zip"
Write-Host "SHA256:  $hash"
Remove-Item $stage -Recurse -Force
