[CmdletBinding()]
param([string]$Owner = 'DDDFXYqiming', [string]$Name = 'everweave-jrpg', [switch]$ExistingEmpty, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Get-Command py -ErrorAction SilentlyContinue
$prefix = @('-3')
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue; $prefix = @() }
if (-not $python) { throw 'Python 3.11+ is required.' }
$publishArgs = @('tools/publish_private.py', '--owner', $Owner, '--name', $Name)
if ($ExistingEmpty) { $publishArgs += '--existing-empty' }
if ($DryRun) { $publishArgs += '--dry-run' }
& $python.Source @prefix @publishArgs
if ($LASTEXITCODE -ne 0) { throw 'Private publishing stopped. Nothing is ever retried as a public repository.' }
