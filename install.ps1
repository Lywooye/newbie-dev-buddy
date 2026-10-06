# Python 3.9+ is required. Native Windows core workflow is not yet supported;
# use WSL for the core CLI and keep the agent and CodeGraph in that environment.
$ErrorActionPreference = "Stop"
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $PSScriptRoot "scripts/install.py") @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $PSScriptRoot "scripts/install.py") @args
} else {
    throw "Python 3.9+ is required."
}
exit $LASTEXITCODE
