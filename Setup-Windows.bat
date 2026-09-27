@echo off
setlocal
cd /d "%~dp0"
echo Setting up Council Archive. This is needed only once.
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer from python.org, then retry.
  pause
  exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto failed
echo Setup complete. Double-click Start-Archive.bat to open your archive.
pause
exit /b 0
:failed
echo Setup could not finish. Copy the error shown above so we can resolve it.
pause
exit /b 1
