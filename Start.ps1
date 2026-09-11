[CmdletBinding()]
param([string]$Godot = '', [switch]$Demo, [switch]$ServerOnly, [string]$DataDir = '')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = '1'
$keyFile = Join-Path $PSScriptRoot 'deepseek.local.key'
if (-not $env:DEEPSEEK_API_KEY -and (Test-Path -LiteralPath $keyFile)) {
    $secureKey = (Get-Content -LiteralPath $keyFile -Raw).Trim() | ConvertTo-SecureString
    $env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
}
$python = Get-Command py -ErrorAction SilentlyContinue
$prefix = @('-3')
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue; $prefix = @() }
if (-not $python) { throw 'Python 3.11+ is required. Install Python, then run this script again.' }
$argsForGame = @('launch.py')
if ($Godot) { $argsForGame += @('--godot', $Godot) }
if ($Demo) { $argsForGame += '--demo' }
if ($ServerOnly) { $argsForGame += '--server-only' }
if ($DataDir) { $argsForGame += @('--data-dir', $DataDir) }
& $python.Source @prefix @argsForGame
if ($LASTEXITCODE -ne 0) { throw "Everweave exited with code $LASTEXITCODE. See the messages above." }
