$ErrorActionPreference = "Stop"

param(
    [string]$ProjectRoot = "$PSScriptRoot"
)

# Pridedam Ruby i PATH, kad anystyle-cli butu pasiekiamas
$rubyBin = "C:\Ruby34-x64\bin"
if (Test-Path $rubyBin) {
    $env:Path = "$rubyBin;$env:Path"
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python nerastas PATH'e."
}

Set-Location $ProjectRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "==> Kuriu virtualia aplinka .venv"
    python -m venv .venv
}

Write-Host "==> Diegiu/atnaujinu Python priklausomybes"
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "==> Paleidziu Streamlit"
& ".\.venv\Scripts\python.exe" -m streamlit run app.py
