@echo off
title Veterinaria Pepe ^& Pepito
cd /d "%~dp0"

set "PY=venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo Iniciando el sistema...
echo Cuando termine de cargar, se abrira: http://127.0.0.1:5000/login
echo Para detenerlo, cierra esta ventana o pulsa Ctrl+C.
echo.

start "" /b cmd /c "timeout /t 4 >nul & start http://127.0.0.1:5000/login"
"%PY%" app.py

pause