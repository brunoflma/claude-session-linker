param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('3.11', '3.14', '3.15')][string]$Series,
    [Parameter(Mandatory = $true)]
    [ValidateSet('probe', 'validation')][string]$Mode
)
$ErrorActionPreference = 'Stop'
# The image's Python is only the stdlib bootstrap host, never the tested runtime.
# provision.py downloads/extracts a complete pinned PSF runtime including Tcl/Tk.
$bootstrap = (Get-Command python.exe -ErrorAction Stop).Source
& $bootstrap scripts/ci/provision.py --series $Series --mode $Mode
exit $LASTEXITCODE
