function Get-LudditiousGitHubPat {
    if ($env:LUDDITIOUS_GITHUB_PAT) {
        return $env:LUDDITIOUS_GITHUB_PAT.Trim()
    }
    $tokenFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "Github-Access-Token.txt"
    if (-not (Test-Path $tokenFile)) {
        $tokenFile = Join-Path (Split-Path $PSScriptRoot -Parent) "Github-Access-Token.txt"
    }
    if (Test-Path $tokenFile) {
        $raw = (Get-Content -Path $tokenFile -Raw).Trim()
        if ($raw -match '(github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+)') {
            return $Matches[1]
        }
        if ($raw -notmatch '[\r\n=]') {
            return $raw
        }
        throw "Github-Access-Token.txt must contain only a PAT, or a line matching github_pat_... / ghp_..."
    }
    throw "Set LUDDITIOUS_GITHUB_PAT or create Github-Access-Token.txt (gitignored) with a ludditious PAT (repo scope)."
}
