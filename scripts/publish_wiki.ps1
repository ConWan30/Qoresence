# Publishes docs/wiki/ to the GitHub Wiki for this repo.
# Requires the wiki to have at least one page already (GitHub limitation).
param(
    [string]$Repo = "ConWan30/Qoresence",
    [string]$WikiDir = "C:\Users\Contr\Qoresence.wiki"
)

$ErrorActionPreference = "Stop"

# Ensure wiki clone exists
if (-Not (Test-Path "$WikiDir\.git")) {
    if (Test-Path $WikiDir) { Remove-Item -Recurse -Force $WikiDir }
    git clone "https://github.com/$Repo.wiki.git" $WikiDir
}

# Pull latest
cd $WikiDir
git pull origin master 2>$null

# Copy source wiki pages
cp "C:\Users\Contr\Qoresence\docs\wiki\*" . -Recurse -Force

# Commit and push
git add .
if ($?) {
    $msg = "Sync wiki from docs/wiki @ $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    git commit -m "$msg" 2>$null
    git push origin master
    Write-Host "Wiki synced to https://github.com/$Repo/wiki"
}
