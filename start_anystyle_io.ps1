param(
    [string]$AnyStyleRoot = "",
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"

if (-not $AnyStyleRoot) {
    $AnyStyleRoot = Join-Path $env:USERPROFILE "OneDrive\Desktop\anystyle.io"
}

if (-not (Get-Command ruby -ErrorAction SilentlyContinue)) {
    Write-Error "Ruby nerastas. Pirma isidiekite RubyInstaller."
}

if (-not (Get-Command bundle -ErrorAction SilentlyContinue)) {
    Write-Error "Bundler nerastas. Paleiskite: gem install bundler"
}

if (-not (Test-Path $AnyStyleRoot)) {
    Write-Error "Nerastas anystyle.io katalogas: $AnyStyleRoot"
}

Set-Location $AnyStyleRoot

Write-Host "==> anystyle.io: bundle install"
bundle install

Write-Host "==> anystyle.io: db:prepare"
bundle exec rails db:prepare

Write-Host "==> Paleidziu anystyle.io ant http://127.0.0.1:$Port"
Write-Host "==> Access token sukurimui: bundle exec rails console"

bundle exec rails server -p $Port
