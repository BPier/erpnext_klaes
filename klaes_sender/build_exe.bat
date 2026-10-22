@echo off
REM Builds klaes_sender.exe from klaes_sender.py
REM Needs Python installed on this machine (https://www.python.org/downloads/windows/)

cd /d "%~dp0"

pip install pyinstaller
pyinstaller --onefile --console klaes_sender.py

copy /Y config.example.ini dist\config.example.ini
copy /Y sample_order.json dist\sample_order.json

echo.
echo Done. The "dist" folder contains klaes_sender.exe, config.example.ini and sample_order.json
echo Next: copy config.example.ini to config.ini and fill in your settings.
pause