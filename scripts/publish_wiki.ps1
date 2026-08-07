# Publish docs/wiki/*.md to GitHub Wiki (requires Wiki enabled on the repo).
# Usage: .\scripts\publish_wiki.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$wikiSrc = Join-Path $root "docs\wiki"
$tmp = Join-Path $env:TEMP "Qoresence.wiki-publish"

if (-not (Test-Path $wikiSrc)) {
    Write-Error "Missing $wikiSrc"
}

if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }

Write-Host "Cloning wiki..."
git clone "https://github.com/ConWan30/Qoresence.wiki.git" $tmp
if ($LASTEXITCODE -ne 0) {
    Write-Host @"

Wiki clone failed. Enable Wiki in GitHub Settings → Features, then re-run.
Or open: https://github.com/ConWan30/Qoresence/settings
"@
    exit 1
}

Copy-Item (Join-Path $wikiSrc "*.md") $tmp -Force
Push-Location $tmp
git add -A
$status = git status --porcelain
if (-not $status) {
    Write-Host "Wiki already up to date."
    Pop-Location
    exit 0
}
git commit -m "docs(wiki): sync from docs/wiki — novel stack, runbook, roadmap"
git push origin HEAD
Pop-Location
Write-Host "Wiki published: https://github.com/ConWan30/Qoresence/wiki"
