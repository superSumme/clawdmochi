@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
where python >nul 2>nul
if %errorlevel%==0 (
  set PYEXE=python
) else (
  set PYEXE=py
)
%PYEXE% launcher.py
echo.
echo [app exited] press any key to close this window
pause >nul
