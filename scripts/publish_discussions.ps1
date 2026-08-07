# Create GitHub Discussions from docs/discussions/*.md (requires Discussions enabled).
# Usage: .\scripts\publish_discussions.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$dir = Join-Path $root "docs\discussions"

# Resolve repo + category
$repoJson = gh api graphql -f query='
query($o:String!,$n:String!){
  repository(owner:$o,name:$n){
    id
    hasDiscussionsEnabled
    discussionCategories(first:20){ nodes { id name } }
  }
}' -f o=ConWan30 -f n=Qoresence | ConvertFrom-Json

$repo = $repoJson.data.repository
if (-not $repo.hasDiscussionsEnabled) {
    Write-Host "Discussions disabled. Enable in Settings → Features, then re-run."
    exit 1
}

$repoId = $repo.id
$ann = $repo.discussionCategories.nodes | Where-Object { $_.name -eq "Announcements" } | Select-Object -First 1
if (-not $ann) {
    $ann = $repo.discussionCategories.nodes | Select-Object -First 1
}
if (-not $ann) {
    Write-Error "No discussion categories found."
}
Write-Host "Using category: $($ann.name) ($($ann.id))"

Get-ChildItem $dir -Filter "*.md" | Sort-Object Name | ForEach-Object {
    $raw = Get-Content $_.FullName -Raw
    $title = $_.BaseName
    $body = $raw
    if ($raw -match '(?s)^---\s*\r?\ntitle:\s*"(.*?)"\s*\r?\ncategory:\s*(\w+)\s*\r?\n---\s*\r?\n(.*)$') {
        $title = $Matches[1]
        $body = $Matches[3].Trim()
    }
    Write-Host "Creating: $title"
    $result = gh api graphql -f query='
mutation($repo:ID!,$cat:ID!,$title:String!,$body:String!){
  createDiscussion(input:{repositoryId:$repo,categoryId:$cat,title:$title,body:$body}){
    discussion { url }
  }
}' -f repo=$repoId -f cat=$ann.id -f title=$title -f body=$body
    Write-Host $result
}

Write-Host "Done. https://github.com/ConWan30/Qoresence/discussions"
