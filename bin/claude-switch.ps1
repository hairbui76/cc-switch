#!/usr/bin/env pwsh
# Locates a usable Python and hands off to bin/claude-accounts.py.

$launcher = Join-Path $PSScriptRoot 'claude-accounts.py'

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
    Write-Error 'Python 3.7+ not found. Install it, or set $env:CLAUDE_SWITCH_PYTHON'
    exit 1
}

# Make Python emit UTF-8 so the output renders on legacy code pages.
$env:PYTHONIOENCODING = 'utf-8'

& $py $launcher @args
exit $LASTEXITCODE
