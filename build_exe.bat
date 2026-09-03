@echo off
echo ==============================================
echo   Сборка QWERTY Switcher в единый .EXE файл
echo ==============================================

pyinstaller --noconsole --onefile --clean --name "QWERTY_Switcher" main.py

echo.
echo Сборка завершена! Исполняемый файл находится в папке dist\QWERTY_Switcher.exe
pause
