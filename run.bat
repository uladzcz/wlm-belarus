@echo off
chcp 65001 > nul
echo Запуск інтэрактыўнай карты «Вікі любіць славутасці — Беларусь»...
start http://localhost:8085
py server.py
pause
