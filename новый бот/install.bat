@echo off
REM Скрипт для установки зависимостей

echo.
echo ====================================
echo Yandex Phone Checker - Установка
echo ====================================
echo.

echo 1. Обновляем pip...
python -m pip install --upgrade pip

echo.
echo 2. Устанавливаем зависимости...
pip install -r requirements_server.txt

echo.
echo 3. Проверяем Tesseract OCR...
python -c "import checker; checker.check_tesseract_installed()"

echo.
echo ====================================
echo Установка завершена!
echo ====================================
echo.
echo Для запуска бота: python bot_new.py
echo Для запуска сервера: python server.py
echo.
pause
