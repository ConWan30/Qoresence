# Publishes docs/wiki/ to the GitHub Wiki for this repo.
# Requires the wiki to have at least one page already (GitHub limitation).
param(
    [string]$Repo = "ConWan30/Qoresence",
    [string]$WikiDir = "..\Qoresence.wiki"
)

$ErrorActionPreference = "Stop"

# Ensure wiki clone exists
if (-Not (Test-Path "$WikiDir\.git")) {
    if (Test-Path $WikiDir) { Remove-Item -Recurse -Force $WikiDir }
    git clone "https://github.com/$Repo.wiki.git" $WikiDir
}

# Pull latest
cd $WikiDir
$ErrorActionPreference = "Continue"
git pull --quiet origin master 2>&1 | Out-Null
$ErrorActionPreference = "Stop"

# Copy source wiki pages
$SourceWiki = Join-Path (Split-Path -Parent $PSScriptRoot) "docs\wiki"
Copy-Item (Join-Path $SourceWiki "*") . -Recurse -Force

# Commit and push
$ErrorActionPreference = "Continue"
git add .
$msg = "Sync wiki from docs/wiki @ $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git commit -m "$msg" 2>&1 | Out-Null
$ErrorActionPreference = "Stop"
git push origin master
