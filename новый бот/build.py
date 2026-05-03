"""
Скрипт сборки бота в .exe файл
"""
import subprocess
import sys
import os
import shutil

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def check_tesseract():
    """Проверка установки Tesseract OCR"""
    print("🔍 Проверка Tesseract OCR...")
    
    tesseract_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f" Tesseract найден в PATH: {result.stdout.split()[0]}")
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    for path in tesseract_paths:
        if os.path.exists(path):
            print(f"Tesseract найден: {path}")
            return True
    
    print("\n" + "="*60)
    print(" Tesseract OCR не найден!")
    print("="*60)
    print("\nДля работы бота необходимо установить Tesseract OCR:")
    print("1. Скачайте установщик: tesseract-ocr-w64-setup-5.5.0.20241111.exe")
    print("   https://github.com/UB-Mannheim/tesseract/wiki")
    print("\n2. Запустите установщик и следуйте инструкциям")
    print("   Рекомендуется установить в путь по умолчанию:")
    print("   C:\\Program Files\\Tesseract-OCR")
    print("\n3. При установке отметьте галочку:")
    print("   ☑ Add Tesseract to the PATH")
    print("\n4. После установки перезапустите этот скрипт")
    print("="*60)
    
    return False


def install_dependencies():
    print("\nУстановка зависимостей...")
    
    try:
        import PyInstaller
        print("PyInstaller уже установлен")
        return True
    except ImportError:
        pass
    
    try:
        print(" Установка зависимостей через uv sync...")
        result = subprocess.run(
            ["uv", "sync"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print("Зависимости установлены")
            
            try:
                import PyInstaller
                return True
            except ImportError:
                pass
        
        print("uv sync не удался, пробуем pip...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "pyinstaller", "--quiet"
        ])
        print("PyInstaller установлен через pip")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Ошибка установки: {e}")
        return False
    except FileNotFoundError:
        print("uv не найден. Установите uv или установите PyInstaller вручную:")
        print("   pip install pyinstaller")
        return False


def build_exe():
    print("\n🔨 Сборка .exe файла...")
    
    spec_content = '''
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['bot.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'easyocr',
        'pytesseract',
        'telebot',
        'requests',
        'PIL',
        'numpy',
        'cv2',
        'io',
        'json',
        're',
        'uuid',
        'time',
        'collections',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='YandexCheckerBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
'''
    
    spec_file = 'YandexCheckerBot.spec'
    with open(spec_file, 'w', encoding='utf-8') as f:
        f.write(spec_content)
    
    print(f"📄 Создан spec файл: {spec_file}")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "PyInstaller",
            "--clean",
            "--noconfirm",
            spec_file
        ])
        
        exe_path = os.path.join('dist', 'YandexCheckerBot.exe')
        if os.path.exists(exe_path):
            print(f"\nСборка завершена!")
            print(f".exe файл: {os.path.abspath(exe_path)}")
            
            shutil.copy(exe_path, 'YandexCheckerBot.exe')
            print(f" Копия сохранена: {os.path.abspath('YandexCheckerBot.exe')}")
            
            return True
        else:
            print(".exe файл не найден после сборки")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"Ошибка сборки: {e}")
        return False


def main():
    print("="*60)
    print("🔧 YandexCheckerBot - Сборка в .exe")
    print("="*60)
    
    if not check_tesseract():
        print("\nСборка отменена: Tesseract OCR не установлен")
        print("\nНажмите Enter для выхода...")
        try:
            input()
        except EOFError:
            pass
        sys.exit(1)
    
    if not install_dependencies():
        print("\nСборка отменена: не удалось установить зависимости")
        print("\nНажмите Enter для выхода...")
        try:
            input()
        except EOFError:
            pass
        sys.exit(1)
    
    if not build_exe():
        print("\nСборка не удалась")
        print("\nНажмите Enter для выхода...")
        try:
            input()
        except EOFError:
            pass
        sys.exit(1)
    
    print("\n" + "="*60)
    print("Сборка завершена успешно!")
    print("="*60)
    print("\n Файлы:")
    print("   • YandexCheckerBot.exe (в корне проекта)")
    print("   • dist/YandexCheckerBot.exe")
    print("\n Для запуска бота:")
    print("   1. Убедитесь, что Tesseract OCR установлен")
    print("   2. Запустите YandexCheckerBot.exe")
    print("="*60)
    print("\nНажмите Enter для выхода...")
    try:
        input()
    except EOFError:
        pass


if __name__ == "__main__":
    main()
