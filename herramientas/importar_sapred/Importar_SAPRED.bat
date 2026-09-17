@echo off
cd /d "%~dp0"
title Importar SAPRED - IETABA

if not exist node_modules (
    echo Primera vez usando esto: instalando lo necesario, un momento...
    call npm install
    if errorlevel 1 (
        echo.
        echo No se pudo instalar. Revisa que tengas internet y Node.js instalado.
        pause
        exit /b 1
    )
)

node importar_sapred.js

pause
