# Sobe o app FastAPI de exemplo do logcenter_sdk.
# Cria o venv, instala dependencias (inclui a SDK local em modo editavel),
# gera o .env a partir do .env.example se ainda nao existir, e roda via uvicorn.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Criando venv..."
    python -m venv .venv
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$venvPip = Join-Path $PSScriptRoot ".venv\Scripts\pip.exe"

Write-Host "Instalando dependencias..."
& $venvPip install -q -r requirements.txt
& $venvPip install -q -e "..\..\python"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Criado .env a partir de .env.example - edite se quiser apontar pra outro LogCenter."
}

Write-Host "Subindo FastAPI em http://localhost:8001 (docs em /docs) ..."
& $venvPython -m uvicorn main:app --reload --port 8001
