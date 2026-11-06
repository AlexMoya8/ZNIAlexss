@echo off
chcp 65001 >nul
title Sistema Energia ZNI
cd /d "%~dp0"

set PY=python
where python >nul 2>nul || set PY=py
%PY% --version >nul 2>nul || (
  echo No se encontro Python. Instale Python 3.10 o superior desde https://www.python.org y marque "Add python.exe to PATH".
  pause
  exit /b 1
)

echo [1/2] Verificando librerias (la primera vez tarda unos minutos)...
%PY% -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
  echo No se pudieron instalar las librerias. Revise su conexion a internet.
  pause
  exit /b 1
)

netstat -ano | findstr ":8000 " | findstr LISTENING >nul && (
  echo.
  echo Ya hay otro sistema abierto en el puerto 8000, quizas una version anterior.
  echo Cierre la otra ventana negra del sistema y vuelva a abrir iniciar.bat.
  pause
  exit /b 1
)

echo [2/2] Iniciando el sistema en http://127.0.0.1:8000  (cierre esta ventana para apagarlo)
echo El navegador se abre solo cuando el sistema este listo.
start "" /b %PY% scripts\abrir_navegador.py
%PY% -m uvicorn app.main:app --port 8000
pause
