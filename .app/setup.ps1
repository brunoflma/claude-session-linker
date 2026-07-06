# ============================================================================
# Claude Session Linker - setup do ambiente (fonte unica de verdade)
# ============================================================================
# Detecta um Python 3.10+, (re)cria o venv isolado em .app\venv, instala as
# dependencias e verifica os imports da GUI. Escreve um resultado legivel em
# .app\logs\setup-result.txt e sai com:
#   0 tudo pronto
#   2 Python ausente
#   3 falha ao criar venv
#   4 falha ao instalar dependencias
#   5 falha ao importar dependencias da GUI
#   6 falha de permissao/arquivo em uso
#
# Uso recomendado: duplo clique em "00 - Setup Claude Session Linker.vbs"
# Uso manual:      powershell -NoProfile -ExecutionPolicy Bypass -File .app\setup.ps1
# ============================================================================

param(
    [switch]$PauseOnExit,
    [switch]$RecreateVenv
)

$appDir  = $PSScriptRoot
$venv    = Join-Path $appDir "venv"
$req     = Join-Path $appDir "requirements.txt"
$logDir  = Join-Path $appDir "logs"
$result  = Join-Path $logDir "setup-result.txt"
$minMajor, $minMinor = 3, 10

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

try {
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
} catch {
    Write-Host "Nao foi possivel criar .app\logs. Mova o projeto para uma pasta gravavel e tente novamente."
    if ($PauseOnExit) { Read-Host "Pressione Enter para fechar" | Out-Null }
    exit 6
}

function Finish([int]$code, [string]$msg) {
    try {
        Set-Content -Path $result -Value ("STATUS=$code`n$msg") -Encoding UTF8
    } catch {
        Write-Host "Aviso: nao foi possivel gravar .app\logs\setup-result.txt"
    }
    Write-Host ""
    Write-Host $msg
    if ($PauseOnExit) { Read-Host "Pressione Enter para fechar" | Out-Null }
    exit $code
}

function Test-PythonVersion([string]$pythonCommand, [string[]]$arguments) {
    try {
        $verOut = & $pythonCommand @arguments -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $verOut) {
            $parts = $verOut.Trim().Split(".")
            $maj = [int]$parts[0]; $min = [int]$parts[1]
            return ($maj -gt $minMajor -or ($maj -eq $minMajor -and $min -ge $minMinor))
        }
    } catch { }
    return $false
}

function Find-Python {
    $py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($ver in @("3.14", "3.13", "3.12", "3.11", "3.10")) {
            $arg = "-$ver"
            if (Test-PythonVersion $py.Source @($arg)) {
                return @{ Command = $py.Source; Arguments = @($arg) }
            }
        }
    }

    $candidates = @()
    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($python) { $candidates += $python.Source }

    foreach ($ver in @("314", "313", "312", "311", "310")) {
        $path = "C:\Python$ver\python.exe"
        if (Test-Path $path) { $candidates += $path }
    }

    $localPrograms = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path $localPrograms) {
        try {
            $candidates += Get-ChildItem -Path $localPrograms -Recurse -Filter python.exe -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty FullName
        } catch { }
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-PythonVersion $candidate @()) {
            return @{ Command = $candidate; Arguments = @() }
        }
    }
    return $null
}

Write-Host "Claude Session Linker 1.5 - configurando ambiente..."

$python = Find-Python
if (-not $python) {
    Finish 2 "Python $minMajor.$minMinor+ nao encontrado. Instale em https://python.org e tente de novo."
}
Write-Host ("Python encontrado: " + $python.Command + " " + ($python.Arguments -join " "))

if ($RecreateVenv -and (Test-Path $venv)) {
    Write-Host "Recriando venv isolado em .app\venv ..."
    try {
        Remove-Item -LiteralPath $venv -Recurse -Force
    } catch {
        Finish 6 "Nao foi possivel remover .app\venv. Feche o aplicativo e tente novamente."
    }
}

$venvPy = Join-Path $venv "Scripts\python.exe"
if ((Test-Path $venv) -and -not (Test-Path $venvPy)) {
    Write-Host "venv existente esta incompleto; recriando..."
    try {
        Remove-Item -LiteralPath $venv -Recurse -Force
    } catch {
        Finish 6 "Nao foi possivel recriar .app\venv. Feche processos Python abertos e tente novamente."
    }
}

if (-not (Test-Path $venv)) {
    Write-Host "Criando venv isolado em .app\venv ..."
    & $python.Command @($python.Arguments) -m venv $venv
    if ($LASTEXITCODE -ne 0) { Finish 3 "Falha ao criar o venv." }
}

if (-not (Test-Path $venvPy)) { Finish 3 "venv criado mas python.exe nao encontrado em Scripts\." }

Write-Host "Instalando dependencias..."
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r $req
if ($LASTEXITCODE -ne 0) { Finish 4 "Falha ao instalar dependencias (veja requirements.txt)." }

Write-Host "Verificando import da GUI..."
& $venvPy -c "import customtkinter, PIL; print('ok')" | Out-Null
if ($LASTEXITCODE -ne 0) { Finish 5 "Dependencias instaladas mas import falhou (customtkinter/pillow)." }

Finish 0 "Ambiente pronto. Use o atalho 'Claude Session Linker.vbs' para abrir."
