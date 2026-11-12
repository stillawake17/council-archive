@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup-Windows.bat first.
  pause
  exit /b 1
)
echo Comparing each built-in council website with the saved examples. This takes about two minutes.
echo.
".venv\Scripts\python.exe" tests\council_pages.py check
echo.
pause
