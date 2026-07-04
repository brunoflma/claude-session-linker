# ============================================================================
# Claude Session Linker - setup do ambiente (fonte unica de verdade)
# ============================================================================
# Detecta um Python 3.10+, (re)cria o venv isolado em .app\venv, instala as
# dependencias e VERIFICA os imports da GUI. Escreve um resultado legivel em
# .app\logs\setup-result.txt e sai com: 0 (tudo pronto) | 2-5 (falha de
# Python/venv/deps), para o launcher .vbs decidir o que mostrar.
#
# Uso:  powershell -NoProfile -ExecutionPolicy Bypass -File .app\setup.ps1
# ============================================================================

$appDir  = $PSScriptRoot
$venv    = Join-Path $appDir "venv"
$req     = Join-Path $appDir "requirements.txt"
$logDir  = Join-Path $appDir "logs"
$result  = Join-Path $logDir "setup-result.txt"
$minMajor, $minMinor = 3, 10

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

function Finish([int]$code, [string]$msg) {
    Set-Content -Path $result -Value ("STATUS=$code`n$msg") -Encoding UTF8
    Write-Host ""
    Write-Host $msg
    exit $code
}

function Find-Python {
    $candidates = @()
    foreach ($cmd in @("py", "python")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { $candidates += $found.Source }
    }
    foreach ($ver in @("314", "313", "312", "311", "310")) {
        $p = "C:\Python$ver\python.exe"
        if (Test-Path $p) { $candidates += $p }
    }
    foreach ($c in $candidates) {
        try {
            $verOut = & $c -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $verOut) {
                $parts = $verOut.Trim().Split(".")
                $maj = [int]$parts[0]; $min = [int]$parts[1]
                if ($maj -gt $minMajor -or ($maj -eq $minMajor -and $min -ge $minMinor)) {
                    return $c
                }
            }
        } catch { }
    }
    return $null
}

Write-Host "Claude Session Linker - configurando ambiente..."

$python = Find-Python
if (-not $python) {
    Finish 2 "Python $minMajor.$minMinor+ nao encontrado. Instale em https://python.org e tente de novo."
}
Write-Host "Python encontrado: $python"

if (-not (Test-Path $venv)) {
    Write-Host "Criando venv isolado em .app\venv ..."
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0) { Finish 3 "Falha ao criar o venv." }
}

$venvPy = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPy)) { Finish 3 "venv criado mas python.exe nao encontrado em Scripts\." }

Write-Host "Instalando dependencias..."
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r $req
if ($LASTEXITCODE -ne 0) { Finish 4 "Falha ao instalar dependencias (veja requirements.txt)." }

Write-Host "Verificando import da GUI..."
& $venvPy -c "import customtkinter, PIL; print('ok')" | Out-Null
if ($LASTEXITCODE -ne 0) { Finish 5 "Dependencias instaladas mas import falhou (customtkinter/pillow)." }

Finish 0 "Ambiente pronto. Use o atalho 'Claude Session Linker.vbs' para abrir."
