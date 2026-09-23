# Push main only (push to main also triggers publish unless only version.txt changed).
# Usage: .\scripts\push-to-ludditious.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lib\github-pat.ps1"
Set-Location (Split-Path $PSScriptRoot -Parent)

$pat = Get-LudditiousGitHubPat
$remote = "https://ludditious:$pat@github.com/ludditious/AdGuardHome-ToolBox.git"
Write-Host "Pushing main to ludditious/AdGuardHome-ToolBox ..."
git push $remote HEAD:main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Done. For a guaranteed GHCR build after version.txt-only commits, run .\scripts\publish-docker.ps1"
