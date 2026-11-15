@echo off
setlocal
cd /d "%~dp0"

set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.9 or newer is needed. Get it from https://www.python.org/downloads/
  echo When installing, tick "Add python.exe to PATH". Then run this again.
  pause
  exit /b 1
)

if not exist ".venv\.installed" (
  echo First run: setting things up. This takes about a minute.
  if exist ".venv" rmdir /s /q ".venv"
  %PY% -m venv .venv || goto setupfailed
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto setupfailed
  echo ok> ".venv\.installed"
)

".venv\Scripts\python.exe" -m peerpatch_linkedin %*
set "STATUS=%ERRORLEVEL%"
pause
exit /b %STATUS%

:setupfailed
if exist ".venv" rmdir /s /q ".venv"
echo Setup failed. Check your internet connection and run this again.
pause
exit /b 1
