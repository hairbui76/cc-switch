#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Point your PowerShell profile at *this checkout* - for hacking on the tool.

.DESCRIPTION
    Commands run straight out of the working tree, so an edit takes effect with
    no reinstall, and updates come from `git pull`.

    For normal use install a managed copy instead, which can self-update:
      irm https://raw.githubusercontent.com/hairbui76/cc-switch/main/install.ps1 | iex
#>

$ErrorActionPreference = 'Stop'

$dir = $PSScriptRoot
$begin = '# >>> cc-switch >>>'
$end = '# <<< cc-switch <<<'
# Markers from before the repo was renamed, stripped too so a re-run replaces
# an old block rather than leaving a second one behind.
$oldBegin = '# >>> claude-code-multi-account-switch >>>'
$oldEnd = '# <<< claude-code-multi-account-switch <<<'

# --- sanity check -----------------------------------------------------------
# Candidates must be *probed*, not just found on PATH: on Windows `python3` is
# usually the Microsoft Store stub, which exists but is not an interpreter.
function Resolve-Python {
    foreach ($name in @($env:CLAUDE_SWITCH_PYTHON, 'python3', 'python', 'py')) {
        if (-not $name) { continue }
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        & $cmd.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return $cmd.Source }
    }
    return $null
}

$py = Resolve-Python
if (-not $py) {
    Write-Host '[xx] Python 3.7+ not found.' -ForegroundColor Red
    Write-Host '     Install from https://python.org or the Microsoft Store, then re-run.'
    exit 1
}
$version = (& $py -c 'import sys; print("%d.%d" % sys.version_info[:2])').Trim()
Write-Host "[ok] Python $version at $py" -ForegroundColor Green

# --- write the profile block ------------------------------------------------
$switch = Join-Path $dir 'bin\claude-switch.ps1'

$block = @"
$begin
# Managed by init.ps1 (dev checkout at $dir) - edit the repo, not this block.
function claude-switch { & '$switch' @args }
function claude-next   { & '$switch' next @args }
function claude-usage  { & '$switch' usage @args }
function claude-sync   { & '$switch' sync @args }
$end
"@

$profilePath = $PROFILE.CurrentUserAllHosts
$profileDir = Split-Path $profilePath -Parent
if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Path $profileDir -Force | Out-Null }

$existing = if (Test-Path $profilePath) { Get-Content $profilePath -Raw } else { '' }

# Drop any previously installed block so re-running stays idempotent.
$cleaned = $existing
foreach ($pair in @(@($begin, $end), @($oldBegin, $oldEnd))) {
    $pattern = [regex]::Escape($pair[0]) + '.*?' + [regex]::Escape($pair[1])
    $cleaned = [regex]::Replace($cleaned, $pattern, '', 'Singleline')
}
$cleaned = $cleaned.TrimEnd()

$updated = if ($cleaned) { "$cleaned`r`n`r`n$block`r`n" } else { "$block`r`n" }
Set-Content -Path $profilePath -Value $updated -Encoding UTF8

Write-Host "[ok] Installed into $profilePath" -ForegroundColor Green
Write-Host ''
Write-Host 'Run this to activate now:' -ForegroundColor Cyan
Write-Host "  . `$PROFILE.CurrentUserAllHosts"
Write-Host '  (or just open a new terminal)'
Write-Host ''
Write-Host 'Commands:'
Write-Host '  claude-switch save <name>   Save the account you are logged in as'
Write-Host '  claude-switch <name>        Switch to an account'
Write-Host '  claude-switch list          List saved accounts'
Write-Host '  claude-switch status        Show the current account'
Write-Host '  claude-next                 Switch to the next account'
Write-Host '  claude-usage                Usage for every account'
Write-Host '  claude-switch doctor        Diagnose setup problems'
Write-Host ''
Write-Host 'This is a dev checkout: update it with `git pull`.'
Write-Host '`claude-switch update` only works on a managed install.'
Write-Host ''
Write-Host 'Upgrading from v1? Run: claude-switch migrate' -ForegroundColor Yellow
