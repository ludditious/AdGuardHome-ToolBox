# Push main to ludditious/AdGuardHome-ToolBox and ensure GHCR publish runs.
# PAT: LUDDITIOUS_GITHUB_PAT or repo-root Github-Access-Token.txt (never commit).
# Usage: .\scripts\publish-docker.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lib\github-pat.ps1"
Set-Location (Split-Path $PSScriptRoot -Parent)

$pat = Get-LudditiousGitHubPat
$repo = "ludditious/AdGuardHome-ToolBox"
$remote = "https://ludditious:$pat@github.com/$repo.git"

Write-Host "Pushing main ..."
git push $remote HEAD:main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Triggering Publish Docker image workflow ..."
$headers = @{
    Authorization = "Bearer $pat"
    Accept        = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}
$body = @{ ref = "main" } | ConvertTo-Json
Invoke-RestMethod -Method Post `
    -Uri "https://api.github.com/repos/$repo/actions/workflows/docker-publish.yml/dispatches" `
    -Headers $headers `
    -Body $body `
    -ContentType "application/json"

Write-Host "Publish started. Image: ghcr.io/ludditious/adguardhome-toolbox:latest"
Write-Host "Actions: https://github.com/$repo/actions/workflows/docker-publish.yml"
Write-Host ""
Write-Host "If the job fails with write_package on a NEW repo, link the package to this repo:"
Write-Host "  GitHub -> Your packages -> adguardhome-toolbox -> Package settings ->"
Write-Host "  Manage Actions access -> add ludditious/AdGuardHome-ToolBox (Write)."
Write-Host "Also: repo Settings -> Actions -> General -> Workflow permissions -> Read and write."
