@echo off
chcp 65001 >nul
title A-fid gestion
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    set PY=python
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PY=py -3
    ) else (
        echo Python n'est pas installe.
        echo Telechargez-le ici : https://www.python.org/downloads/
        echo Cochez "Add python.exe to PATH" pendant l'installation.
        pause
        exit /b 1
    )
)

echo Installation des dependances si besoin...
%PY% -m pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo Echec de l'installation des dependances.
    pause
    exit /b 1
)

echo Lancement de A-fid gestion...
%PY% app.py
pause
