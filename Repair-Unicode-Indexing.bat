@echo off
setlocal
cd /d "%~dp0"
echo Close the Council Archive launcher before continuing.
pause
if not exist .venv\Scripts\python.exe (
 echo Copy BOTH Repair-Unicode-Indexing.bat and repair_unicode_indexing.py
 echo into your existing app folder beside Start-Archive.bat, then retry.
 pause
 exit /b 1
)
.venv\Scripts\python.exe repair_unicode_indexing.py
if errorlevel 1 (
 echo Repair did not complete. Please send the message above.
 pause
 exit /b 1
)
echo Start the app again and click Index existing archive.
echo Completed unchanged files will be skipped. Do not delete the database.
pause
