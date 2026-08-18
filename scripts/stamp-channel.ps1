#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)][string]$InputExe,
    [Parameter(Mandatory = $true)][string]$Code,
    [string]$Output = "",
    [ValidateSet("yizhi", "zhouyi")][string]$Product = "yizhi"
)
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "stamp-channel.py"
$argsList = @($script, "-i", $InputExe, "-c", $Code, "--product", $Product)
if ($Output) { $argsList += @("-o", $Output) }
& python @argsList
exit $LASTEXITCODE
