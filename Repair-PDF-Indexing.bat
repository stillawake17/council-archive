@echo off
setlocal
cd /d "%~dp0"
echo Close the Council Archive launcher before continuing.
echo This repair installs the missing PDF font dependency.
echo It does not delete PDFs or your saved search index.
pause
if not exist .venv\Scripts\python.exe (
 echo No app environment was found here.
 echo Copy this repair file into the folder containing Start-Archive.bat and .venv, then run it there.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m pip install "fonttools>=4,<5"
if errorlevel 1 (
 echo Installation failed. Please copy the error shown above.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -c "from fontTools import version; print('fontTools installed:', version)"
if errorlevel 1 (
 echo The installation could not be verified. Please copy the error above.
 pause
 exit /b 1
)
echo Repair complete. Open Start-Archive.bat, then click Index existing archive.
echo Previously indexed unchanged files will be skipped.
pause
