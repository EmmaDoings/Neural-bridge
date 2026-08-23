$ErrorActionPreference = "Stop"

"Starting Neural Bridge API and web app"

python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

Start-Process powershell -ArgumentList "-NoExit", "-Command", "& `"$PWD\.venv\Scripts\python.exe`" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend"

Set-Location frontend
npm install
npm run dev
