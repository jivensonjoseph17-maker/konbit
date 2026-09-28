# KONMBIT — demare sevè API a (http://127.0.0.1:8000)
# Itilizasyon, depi rasin repo a:   cd backend; .\demare.ps1
# Mache avèk oswa san "(venv)": li sèvi ak uvicorn ki nan venv la dirèkteman.
# Pou kanpe l: Ctrl+C.

Set-Location $PSScriptRoot
$uvicorn = Join-Path $PSScriptRoot "venv\Scripts\uvicorn.exe"

if (-not (Test-Path $uvicorn)) {
    Write-Host "ERE: $uvicorn pa egziste. Kreye venv la anvan (python -m venv venv)." -ForegroundColor Red
    exit 1
}

& $uvicorn app.main:app --reload
