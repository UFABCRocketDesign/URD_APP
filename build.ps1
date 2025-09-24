\
# build.ps1 — create venv, install deps, run, and build exe
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

# run to test:
python main.py

# build exe
pip install pyinstaller
pyinstaller --name RocketGS --noconsole --onedir main.py --collect-all PySide6
Write-Host "`nBuild complete. Check .\dist\RocketGS\RocketGS.exe"
