@echo off
chcp 65001 >nul
title A-fid gestion - reseau
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
        pause
        exit /b 1
    )
)

echo Installation des dependances si besoin...
%PY% -m pip install -r requirements.txt -q
echo.
echo Mode reseau : Windows + telephone sur le meme Wi-Fi.
echo Laissez cette fenetre ouverte.
echo.
%PY% app.py --reseau
pause
