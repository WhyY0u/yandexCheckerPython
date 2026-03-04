@echo off
chcp 1251 >nul
echo ============================================================
echo YandexCheckerBot - Запуск через Python
echo ============================================================
echo.

:: Проверка Tesseract в PATH
set TESSERACT_PATH=
where tesseract >nul 2>&1 && set TESSERACT_PATH=1

:: Проверка в стандартном пути
if not defined TESSERACT_PATH (
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        set TESSERACT_PATH=C:\Program Files\Tesseract-OCR
        PATH=%TESSERACT_PATH%;%PATH%
        echo Tesseract найден в: %TESSERACT_PATH%
    )
)

:: Если не найден
if not defined TESSERACT_PATH (
    echo ОШИБКА: Tesseract OCR не найден!
    echo.
    echo Для установки Tesseract OCR:
    echo 1. Скачайте: tesseract-ocr-w64-setup-5.5.0.20241111.exe
    echo    https://github.com/UB-Mannheim/tesseract/wiki
    echo.
    echo 2. Запустите установщик
    echo.
    echo 3. ВАЖНО: Отметьте галочку:
    echo    [x] Add Tesseract to the PATH
    echo.
    echo 4. Перезапустите этот файл после установки
    echo.
    echo ============================================================
    pause
    exit /b 1
)

echo Tesseract найден: OK
echo.

:: Проверка uv
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo ОШИБКА: uv не найден!
    echo.
    echo Установите uv: https://docs.astral.sh/uv/getting-started/installation/
    echo.
    pause
    exit /b 1
)

:: Запуск бота
echo Запуск бота...
echo.
uv run python bot.py

if %errorlevel% neq 0 (
    echo.
    echo Бот завершил работу с ошибкой
    pause
)
