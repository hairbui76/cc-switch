#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One-line installer for claude-code-multi-account-switch.

.DESCRIPTION
    irm https://raw.githubusercontent.com/hairbui76/claude-code-multi-account-switch/main/install.ps1 | iex

    Needs PowerShell 5+ and Python 3.7+. Does not need git.
    Re-running it is also how you upgrade, though `claude-switch update` is
    quicker once installed.

    Environment overrides:
      CLAUDE_SWITCH_CHANNEL  main (every push, default) | stable (git tags)
      CLAUDE_SWITCH_HOME     install root
      CLAUDE_SWITCH_BIN      directory the claude-* launchers go into
      CLAUDE_SWITCH_PYTHON   interpreter to use
      CLAUDE_SWITCH_REPO     owner/name to install from
#>

$ErrorActionPreference = 'Stop'

$repo = if ($env:CLAUDE_SWITCH_REPO) { $env:CLAUDE_SWITCH_REPO } else { 'hairbui76/claude-code-multi-account-switch' }
$channel = if ($env:CLAUDE_SWITCH_CHANNEL) { $env:CLAUDE_SWITCH_CHANNEL } else { 'main' }

# --- interpreter ------------------------------------------------------------
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
$pyVersion = (& $py -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])').Trim()
Write-Host "[ok] Python $pyVersion at $py" -ForegroundColor Green

# --- bootstrap --------------------------------------------------------------
# Only a throwaway copy is fetched here, just enough to run `setup`. That copy
# then resolves the requested channel and installs the real, pinned build, so
# all the install logic lives in one place instead of being duplicated in
# shell, PowerShell and Python.
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("claude-switch-" + [System.Guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null

try {
    Write-Host "[--] fetching $repo"
    $zip = Join-Path $tmp 'bootstrap.zip'
    # A zip rather than a tarball: Expand-Archive is built in, tar.exe is not
    # present before Windows 10 1803.
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri "https://codeload.github.com/$repo/zip/main" -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp -Force

    $boot = Get-ChildItem -Path $tmp -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'bin\claude-accounts.py') } |
        Select-Object -First 1
    if (-not $boot) {
        Write-Host "[xx] the download does not look like $repo" -ForegroundColor Red
        exit 1
    }

    $env:PYTHONIOENCODING = 'utf-8'
    & $py (Join-Path $boot.FullName 'bin\claude-accounts.py') setup --bootstrap --channel $channel
    exit $LASTEXITCODE
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
