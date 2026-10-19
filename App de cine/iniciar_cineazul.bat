@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw cine_azul.py
    exit /b
)
where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pythonw.exe cine_azul.py
    exit /b
)
echo No se encontro pyw o pythonw.exe. Instala Python para Windows y vuelve a intentarlo.
pause
