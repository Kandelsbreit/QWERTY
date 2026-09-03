@echo off
echo ==============================================
echo   Сборка QWERTY Switcher в единый .EXE файл
echo ==============================================

python -m PyInstaller --noconsole --onefile --clean --hidden-import=PIL --hidden-import=pystray --add-data "dict_ru.gz;." --add-data "dict_en.gz;." --name "QWERTY_Switcher" main.py

echo.
echo Сборка завершена! Исполняемый файл находится в папке dist\QWERTY_Switcher.exe
pause
