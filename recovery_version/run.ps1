$scriptPath = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
Set-Location $scriptPath
& .\venv\Scripts\Activate.ps1
python -m app.main
