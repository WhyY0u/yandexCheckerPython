import telebot
import requests
import re
import uuid
import json
import time
import easyocr
from PIL import Image
import io
import numpy as np
from collections import defaultdict
import subprocess
import sys
import os
import pytesseract
from datetime import datetime, timedelta
import warnings

# Игнорировать предупреждения PyTorch о pin_memory
warnings.filterwarnings("ignore", message=".*pin_memory.*")

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BOT_TOKEN = "8666414527:AAE_2LciXEdXo0rGbZSw25xco-3b-1E5XnQ"

bot = telebot.TeleBot(BOT_TOKEN)

_phone_queue = defaultdict(list)
_check_active = defaultdict(bool)

_tesseract_path = None

# Статистика и доверенные лица
_stats_file = "stats.json"
_stats = {
    "users": set(),
    "total_requests": 0,
    "daily_requests": 0,
    "last_reset_date": datetime.now().strftime("%Y-%m-%d")
}
_trusted_users = set()

# ID администратора из переменной окружения (опционально)
_admin_id = os.environ.get("BOT_ADMIN_ID")
if _admin_id:
    _trusted_users.add(_admin_id)


def setup_tesseract_path():
    """Настройка пути к Tesseract для pytesseract"""
    global _tesseract_path
    
    if _tesseract_path:
        tesseract_cmd = os.path.join(_tesseract_path, 'tesseract.exe')
        if os.path.exists(tesseract_cmd):
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            print(f"📍 pytesseract.tesseract_cmd = {tesseract_cmd}")
            return True
    
    standard_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    
    for path in standard_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            _tesseract_path = os.path.dirname(path)
            print(f"📍 pytesseract.tesseract_cmd = {path}")
            return True
    
    return False


def check_tesseract_installed():
    """Проверка установки Tesseract OCR при старте бота"""
    global _tesseract_path
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
            version = result.stdout.split()[0] if result.stdout else "unknown"
            print(f"✅ Tesseract найден в PATH: {version}")
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    for path in tesseract_paths:
        if os.path.exists(path):
            print(f"✅ Tesseract найден: {path}")
            _tesseract_path = os.path.dirname(path)
            if _tesseract_path not in os.environ.get('PATH', ''):
                os.environ['PATH'] = _tesseract_path + os.pathsep + os.environ.get('PATH', '')
            return True
    
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        exe_tesseract = os.path.join(exe_dir, 'tesseract.exe')
        if os.path.exists(exe_tesseract):
            print(f"✅ Tesseract найден в папке приложения: {exe_tesseract}")
            _tesseract_path = exe_dir
            os.environ['PATH'] = exe_dir + os.pathsep + os.environ.get('PATH', '')
            return True
    
    print("\n" + "="*60)
    print("❌ Tesseract OCR не найден!")
    print("="*60)
    print("\n⚠️ Для работы бота необходимо установить Tesseract OCR:")
    print("\n1. Скачайте установщик:")
    print("   tesseract-ocr-w64-setup-5.5.0.20241111.exe")
    print("   https://github.com/UB-Mannheim/tesseract/wiki")
    print("\n2. Запустите установщик и следуйте инструкциям")
    print("   Путь по умолчанию: C:\\Program Files\\Tesseract-OCR")
    print("\n3. ⚠️ Обязательно отметьте галочку:")
    print("   ☑ Add Tesseract to the PATH")
    print("\n4. После установки перезапустите бота")
    print("="*60)
    
    return False


def format_phone_number(phone):
    """
    Преобразование номера в формат +7 XXX XXX-XX-XX
    """
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:] 
    elif len(digits) == 10:
        digits = '7' + digits  
    
    if len(digits) != 11 or not digits.startswith('7'):
        return None
    
    # Форматируем: +7 XXX XXX-XX-XX
    formatted = f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return formatted


def solve_captcha_easyocr(image_url):
    """
    Распознавание текстовой капчи через EasyOCR
    """
    try:
        print(f"🔄 Распознавание капчи по URL: {image_url[:50]}...")
        
        img_response = requests.get(image_url, stream=True)
        if img_response.status_code != 200:
            print(f"❌ Не удалось скачать изображение: {img_response.status_code}")
            return None

        img = Image.open(io.BytesIO(img_response.content))

        reader = easyocr.Reader(['en'], gpu=True, verbose=False)
        img_array = np.array(img)

        results = reader.readtext(img_array)
        print(f"📊 EasyOCR результатов: {len(results)}")
        
        sorted_results = sorted(results, key=lambda x: x[0][0][0])

        texts = [res[1].lower() for res in sorted_results]
        full_text = ' '.join(texts)
        print(f"📝 Распознано: '{full_text}'")

        clean_text = re.sub(r'[^a-z\s]', '', full_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        if clean_text:
            print(f"✅ Очищенный текст: '{clean_text}'")
            return clean_text

        print("❌ Пустой результат после очистки")
        return None
    except Exception as e:
        print(f"❌ Ошибка EasyOCR: {e}")
        return None


def get_csrf_token():
    """
    Получение CSRF-токена из страницы авторизации
    """
    session = requests.Session()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    }

    try:
        response = session.get('https://passport.yandex.ru/auth/', headers=headers)
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None, None

    if response.status_code != 200:
        print(f"❌ Статус ответа: {response.status_code}")
        return None, None

    patterns = [
        (r'window\.__CSRF__\s*=\s*"([^"]+)"', "window.__CSRF__"),
        (r'<meta[^>]*name="csrf-token"[^>]*content="([^"]+)"', "meta csrf-token"),
        (r'<input[^>]*name="_csrf"[^>]*value="([^"]+)"', "input _csrf"),
        (r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', "input csrf_token"),
        (r'"csrfToken"\s*:\s*"([^"]+)"', "JSON csrfToken"),
        (r'csrfToken\s*=\s*"([^"]+)"', "JavaScript csrfToken"),
    ]

    for pattern, description in patterns:
        match = re.search(pattern, response.text, re.IGNORECASE)
        if match:
            csrf = match.group(1)
            print(f"✅ CSRF найден через {description}: {csrf[:20]}...")
            return csrf, session

    for cookie in session.cookies:
        if 'csrf' in cookie.name.lower() or cookie.name == 'yc':
            return cookie.value, session

    print("❌ CSRF не найден")
    return None, session


def get_csrf_with_fresh_headers(session):
    """
    Пробуем с обновлёнными заголовками
    """
    fresh_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }

    response = session.get('https://passport.yandex.ru/auth/', headers=fresh_headers)

    if response.status_code == 200:
        match = re.search(r'window\.__CSRF__\s*=\s*"([^"]+)"', response.text)
        if match:
            return match.group(1)

    return None


def create_track(csrf_token, session):
    """
    Создание трека
    """
    url = "https://passport.yandex.ru/pwl-yandex/api/passport/track/create"
    process_uuid = str(uuid.uuid4())

    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
        'C11n': 'yandex_phone_flow',
        'Content-Type': 'application/json',
        'Origin': 'https://passport.yandex.ru',
        'Priority': 'u=1, i',
        'Referer': 'https://passport.yandex.ru/',
        'Sec-Ch-Prefers-Color-Scheme': 'dark',
        'Sec-Ch-Ua': '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Tractor-Location': '0',
        'Tractor-Non-Proxy': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
        'X-Csrf-Token': csrf_token,
        'Process-Uuid': process_uuid,
    }

    data = {
        "display_language": "ru",
        "language": "ru",
        "country": "kz",
        "app_id": "",
        "app_version_name": "",
        "retpath": "",
        "device_id": "",
        "uid": "",
        "device_connection_type": ""
    }

    try:
        response = session.post(url, headers=headers, json=data)
        print(f"📡 Create track: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            if 'id' in result:
                print(f"✅ Track ID: {result['id']}")
                return result['id']
            else:
                print(f"❌ Нет id в ответе: {result}")
        else:
            print(f"❌ Ошибка create_track: {response.text}")
    except Exception as e:
        print(f"❌ Исключение create_track: {e}")

    return None


def generate_captcha(csrf_token, session, track_id):
    """
    Генерация капчи при получении antifraudScore: captcha
    """
    url = "https://passport.yandex.ru/pwl-yandex/api/passport/captcha/generate"
    process_uuid = str(uuid.uuid4())

    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
        'C11n': 'yandex_phone_flow',
        'Content-Type': 'application/json',
        'Origin': 'https://passport.yandex.ru',
        'Priority': 'u=1, i',
        'Referer': 'https://passport.yandex.ru/',
        'Sec-Ch-Prefers-Color-Scheme': 'dark',
        'Sec-Ch-Ua': '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Tractor-Location': '0',
        'Tractor-Non-Proxy': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
        'X-Csrf-Token': csrf_token,
        'Process-Uuid': process_uuid,
    }

    data = {
        "display_language": "eu",
        "voice": True,
        "scale_factor": 3,
        "type": "wave",
        "track_id": track_id
    }

    try:
        response = session.post(url, headers=headers, json=data)

        if response.status_code == 200:
            captcha_data = response.json()
            return captcha_data
        else:
            return None
    except Exception as e:
        return None


def submit_captcha_and_recheck(csrf_token, session, track_id, phone_number, captcha_key, captcha_answer):
    """
    Отправка ответа капчи и повторная проверка доступности
    """
    captcha_check_url = "https://passport.yandex.ru/pwl-yandex/api/passport/captcha/check"
    process_uuid = str(uuid.uuid4())
    
    captcha_headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
        'C11n': 'yandex_phone_flow',
        'Content-Type': 'application/json',
        'Origin': 'https://passport.yandex.ru',
        'Priority': 'u=1, i',
        'Referer': 'https://passport.yandex.ru/',
        'Sec-Ch-Prefers-Color-Scheme': 'dark',
        'Sec-Ch-Ua': '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Tractor-Location': '0',
        'Tractor-Non-Proxy': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
        'X-Csrf-Token': csrf_token,
        'Process-Uuid': process_uuid,
    }
    
    captcha_data = {
        "answer": captcha_answer,
        "key": captcha_key,
        "track_id": track_id
    }
    
    try:
        print(f"📡 Отправка captcha_check...")
        check_response = session.post(captcha_check_url, headers=captcha_headers, json=captcha_data)
        print(f"📡 Captcha check status: {check_response.status_code}")
        
        if check_response.status_code == 200:
            captcha_result = check_response.json()
            print(f"📊 Captcha result: {captcha_result}")
            
            if not captcha_result.get('correct', False):
                print("❌ Капча неверная!")
                return None
        else:
            print(f"❌ Ошибка captcha check: {check_response.text}")
            return None
    except Exception as e:
        print(f"❌ Исключение captcha check: {e}")
        return None
    
    time.sleep(0.5)
    
    result = check_availability(csrf_token, session, track_id, phone_number)
    
    if result:
        return result
    else:
        return None


def check_availability(csrf_token, session, track_id, phone_number):
    """
    Проверка доступности номера
    """
    url = "https://passport.yandex.ru/pwl-yandex/api/passport/suggest/check_availability"
    process_uuid = str(uuid.uuid4())

    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
        'C11n': 'yandex_phone_flow',
        'Content-Type': 'application/json',
        'Origin': 'https://passport.yandex.ru',
        'Priority': 'u=1, i',
        'Referer': 'https://passport.yandex.ru/',
        'Sec-Ch-Prefers-Color-Scheme': 'dark',
        'Sec-Ch-Ua': '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Tractor-Location': '0',
        'Tractor-Non-Proxy': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
        'X-Csrf-Token': csrf_token,
        'Process-Uuid': process_uuid,
    }

    data = {
        "phone_number": phone_number,
        "track_id": track_id,
        "check_for_push": True,
        "push_suggest_log_all_subscriptions": False
    }

    try:
        response = session.post(url, headers=headers, json=data)
        print(f"📡 Check availability: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"📊 Результат: {json.dumps(result, ensure_ascii=False)[:200]}")
            return result
        else:
            print(f"❌ Ошибка check_availability: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Исключение check_availability: {e}")
        return None


# Глобальный флаг для пропуска капчи
_skip_captcha_flag = {}

def set_skip_flag(chat_id, value=True):
    """Установить флаг пропуска для чата"""
    global _skip_captcha_flag
    _skip_captcha_flag[chat_id] = value

def get_skip_flag(chat_id):
    """Проверить флаг пропуска для чата"""
    global _skip_captcha_flag
    return _skip_captcha_flag.get(chat_id, False)

def clear_skip_flag(chat_id):
    """Очистить флаг пропуска для чата"""
    global _skip_captcha_flag
    if chat_id in _skip_captcha_flag:
        del _skip_captcha_flag[chat_id]


def load_stats():
    """Загрузка статистики и доверенных пользователей из файла"""
    global _stats, _trusted_users
    try:
        if os.path.exists(_stats_file):
            with open(_stats_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _stats["users"] = set(data.get("users", []))
                _stats["total_requests"] = data.get("total_requests", 0)
                _stats["daily_requests"] = data.get("daily_requests", 0)
                _stats["last_reset_date"] = data.get("last_reset_date", datetime.now().strftime("%Y-%m-%d"))
                _trusted_users = set(data.get("trusted_users", []))
            print(f"📊 Статистика загружена: {_stats['total_requests']} всего запросов, {len(_stats['users'])} пользователей")
    except Exception as e:
        print(f"⚠️ Не удалось загрузить статистику: {e}")


def save_stats():
    """Сохранение статистики и доверенных пользователей в файл"""
    global _stats, _trusted_users
    try:
        data = {
            "users": list(_stats["users"]),
            "total_requests": _stats["total_requests"],
            "daily_requests": _stats["daily_requests"],
            "last_reset_date": _stats["last_reset_date"],
            "trusted_users": list(_trusted_users)
        }
        with open(_stats_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Не удалось сохранить статистику: {e}")


def reset_daily_stats_if_needed():
    """Сброс дневной статистики если наступил новый день"""
    global _stats
    today = datetime.now().strftime("%Y-%m-%d")
    if _stats["last_reset_date"] != today:
        _stats["daily_requests"] = 0
        _stats["last_reset_date"] = today
        print("📊 Дневная статистика сброшена")


def add_user_request(chat_id):
    """Добавление пользователя и подсчёт запроса"""
    global _stats
    reset_daily_stats_if_needed()
    _stats["users"].add(str(chat_id))
    _stats["total_requests"] += 1
    _stats["daily_requests"] += 1
    save_stats()


def is_trusted_user(chat_id):
    """Проверка, является ли пользователь доверенным"""
    return str(chat_id) in _trusted_users


def add_trusted_user(chat_id):
    """Добавление пользователя в список доверенных"""
    global _trusted_users
    _trusted_users.add(str(chat_id))
    save_stats()

def solve_captcha_loop(csrf_token, session, track_id, phone, chat_id=None):
    """
    Цикл решения капч до получения hasAvailableAccounts или команды /skip
    """
    attempt = 0

    while True:
        attempt += 1
        print(f"\n🔄 Попытка решения капчи #{attempt}")

        # Проверяем флаг пропуска
        if chat_id and get_skip_flag(chat_id):
            print("⚠️ Получена команда /skip, завершение цикла")
            clear_skip_flag(chat_id)
            return None

        captcha_data = generate_captcha(csrf_token, session, track_id)

        if not captcha_data:
            print("❌ Не удалось получить капчу, повторная попытка...")
            time.sleep(2)
            continue

        print(f"✅ Капча получена, key: {captcha_data.get('key', 'unknown')[:20]}...")

        answer = None

        if 'image_url' in captcha_data:
            auto_answer = solve_captcha_easyocr(captcha_data['image_url'])

            if auto_answer:
                answer = auto_answer
                print(f"✅ Распознанный ответ: {answer}")
            else:
                print("❌ Не удалось распознать капчу, повторная попытка...")
                time.sleep(2)
                continue

        if not answer:
            print("❌ Нет ответа для капчи, повторная попытка...")
            time.sleep(2)
            continue

        print(f"🔄 Отправляем ответ на проверку...")
        result = submit_captcha_and_recheck(csrf_token, session, track_id, phone,
                                            captcha_data['key'], answer)

        if not result:
            print("❌ Не удалось получить результат, повторная попытка...")
            time.sleep(2)
            continue

        print(f"📊 Результат: {json.dumps(result, ensure_ascii=False)[:200]}")

        if 'hasAvailableAccounts' in result:
            return result

        if result.get('antifraudScore') == 'captcha':
            print("⚠️ Снова требуется капча")
            continue

        return result


def check_phone(phone, chat_id=None, formatted_output=False):
    """
    Основная функция проверки номера
    """
    print(f"\n🔍 Начинаем проверку номера: {phone}")
    
    # Подсчёт запроса
    if chat_id:
        add_user_request(chat_id)

    # Получаем CSRF
    csrf_token, session = get_csrf_token()
    if not csrf_token:
        print("❌ Не удалось получить CSRF, пробуем свежие заголовки...")
        csrf_token = get_csrf_with_fresh_headers(session)

    if not csrf_token:
        print("❌ CSRF не получен")
        return None

    print(f"✅ CSRF получен: {csrf_token[:30]}...")

    # Создаём трек
    track_id = create_track(csrf_token, session)
    if not track_id:
        print("❌ Не удалось создать трек")
        return None

    # Проверяем доступность
    result = check_availability(csrf_token, session, track_id, phone)

    if result:
        print(f"📊 antifraudScore: {result.get('antifraudScore')}")

        if result.get('antifraudScore') == 'captcha':
            print("⚠️ Требуется капча, запускаем цикл решения...")
            while True:
                # Проверяем флаг пропуска перед запуском цикла
                if chat_id and get_skip_flag(chat_id):
                    print("⚠️ Получена команда /skip до начала цикла")
                    clear_skip_flag(chat_id)
                    return None

                final_result = solve_captcha_loop(csrf_token, session, track_id, phone, chat_id)

                if final_result:
                    has_available = final_result.get('hasAvailableAccounts', False)
                    print(f"✅ Результат: hasAvailableAccounts={has_available}")
                    return "registered" if has_available else "not_registered"
                else:
                    # Если solve_captcha_loop вернул None - проверяем, была ли команда /skip
                    if chat_id and get_skip_flag(chat_id):
                        clear_skip_flag(chat_id)
                        return None
                    # Иначе повторяем цикл (будет новая генерация капчи)
                    print("⚠️ solve_captcha_loop вернул None, повторяем цикл...")
                    time.sleep(2)
        else:
            # Если нет капчи, проверяем напрямую
            has_available = result.get('hasAvailableAccounts', False)
            print(f"✅ Результат без капчи: hasAvailableAccounts={has_available}")
            return "registered" if has_available else "not_registered"
    else:
        print("❌ check_availability вернул None")

    return None


def process_phone_result(phone, result, chat_id):
    """Форматирование и отправка результата проверки"""
    if result == "registered":
        response = f"✅ Аккаунт зарегистрирован"
    elif result == "not_registered":
        response = f"❌ Аккаунт не зарегистрирован"
    elif result is None:
        response = f"⚠️ Проверка пропущена по команде /skip"
    else:
        response = f"❌ Не удалось проверить номер"
    
    # Если нужен формат с номером
    if len(_phone_queue[chat_id]) > 0 or _check_active[chat_id]:
        response = f"{phone}: {response}"
    
    return response


def process_queue(chat_id):
    """Обработка очереди номеров для чата"""
    global _check_active
    
    # Если уже идёт проверка - выходим
    if _check_active[chat_id]:
        return
    
    _check_active[chat_id] = True
    
    try:
        while _phone_queue[chat_id]:
            # Проверяем флаг пропуска
            if get_skip_flag(chat_id):
                clear_skip_flag(chat_id)
                bot.send_message(chat_id, "⚠️ Проверка остановлена командой /skip")
                break
            
            phone = _phone_queue[chat_id].pop(0)
            
            # Проверяем номер
            result = check_phone(phone, chat_id=chat_id)
            response = process_phone_result(phone, result, chat_id)
            bot.send_message(chat_id, response)
    finally:
        _check_active[chat_id] = False


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Привет! Отправь мне номер телефона для проверки.\n\nФормат: 89212810954 или +79212810954\n\nМожно отправлять несколько номеров:\n- По одному в сообщении\n- Несколько сразу (каждый с новой строки)\n\nИспользуй /skip для пропуска текущей проверки")


@bot.message_handler(commands=['id'])
def get_chat_id(message):
    chat_id = message.chat.id
    bot.reply_to(message, f"🆔 Ваш chat_id: {chat_id}")


def escape_markdown_v2(text):
    """Экранирование специальных символов для MarkdownV2"""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


@bot.message_handler(commands=['add'])
def add_trusted(message):
    chat_id = message.chat.id
    
    if not is_trusted_user(str(chat_id)):
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Использование: /add <chat_id>\n\nПример: /add 123456789")
        return
    
    try:
        new_trusted_id = args[1]
        add_trusted_user(new_trusted_id)
        bot.reply_to(message, f"✅ Пользователь {escape_markdown_v2(str(new_trusted_id))} добавлен в список доверенных лиц", parse_mode="MarkdownV2")
    except ValueError:
        bot.reply_to(message, "❌ Неверный формат chat_id")


@bot.message_handler(commands=['stats'])
def show_stats(message):
    chat_id = message.chat.id
    
    if not is_trusted_user(str(chat_id)):
        bot.reply_to(message, "❌ Доступ запрещён.\n\nИспользуйте команду /id для получения вашего chat_id")
        return
    
    reset_daily_stats_if_needed()
    
    users_count = len(_stats["users"])
    total_requests = _stats["total_requests"]
    daily_requests = _stats["daily_requests"]
    
    stats_text = (
        f"📊 *Статистика бота*\n\n"
        f"👥 Пользователей (написали хотя бы 1 сообщение): {users_count}\n"
        f"📈 Всего запросов: {total_requests}\n"
        f"📅 Запросов за сегодня: {daily_requests}"
    )
    
    bot.reply_to(message, stats_text, parse_mode="Markdown")


@bot.message_handler(commands=['skip'])
def skip_captcha(message):
    chat_id = message.chat.id
    set_skip_flag(chat_id, True)
    bot.reply_to(message, "⚠️ Команда /skip принята. Пропускаю текущую капчу...")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    # Разбиваем сообщение на строки (поддержка нескольких номеров)
    lines = text.split('\n')
    
    # Извлекаем и форматируем номера
    valid_phones = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        formatted_phone = format_phone_number(line)
        if formatted_phone:
            valid_phones.append(formatted_phone)
    
    # Если нет валидных номеров
    if not valid_phones:
        bot.reply_to(message, "❌ Неверный формат номера.\n\nОтправь номер в формате:\n89212810954 или +79212810954\n\nМожно отправлять несколько номеров сразу (каждый с новой строки)")
        return
    
    # Если номер один и нет активной проверки - отвечаем сразу
    if len(valid_phones) == 1 and not _check_active[chat_id] and not _phone_queue[chat_id]:
        phone = valid_phones[0]
        bot.reply_to(message, f"🔍 Проверяю номер {phone}...")
        
        result = check_phone(phone, chat_id=chat_id)
        response = process_phone_result(phone, result, chat_id)
        bot.send_message(chat_id, response)
    else:
        # Добавляем номера в очередь
        _phone_queue[chat_id].extend(valid_phones)
        
        if len(valid_phones) == 1:
            bot.reply_to(message, f"🔍 Номер {valid_phones[0]} добавлен в очередь")
        else:
            bot.reply_to(message, f"🔍 Добавлено номеров: {len(valid_phones)}\nНачинаю проверку...")
        
        # Запускаем обработку очереди
        process_queue(chat_id)


if __name__ == "__main__":
    # Проверка Tesseract перед запуском
    if not check_tesseract_installed():
        print("\n❌ Бот не запущен: Tesseract OCR не установлен")
        try:
            input("\nНажмите Enter для выхода...")
        except EOFError:
            pass
        sys.exit(1)

    # Настраиваем путь для pytesseract
    setup_tesseract_path()

    # Загружаем статистику и доверенных пользователей
    load_stats()

    print("\n🤖 Бот запущен...")
    bot.infinity_polling()
