import telebot
import requests
from requests.adapters import HTTPAdapter, Retry
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
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

warnings.filterwarnings("ignore", message=".*pin_memory.*")

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Загружаем BOT_TOKEN из переменной окружения
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен! Создайте .env файл с BOT_TOKEN=your_token")

MAX_CONCURRENT_CHECKS = 15
_check_semaphore = threading.Semaphore(MAX_CONCURRENT_CHECKS)

_executor = ThreadPoolExecutor(max_workers=20)

_check_progress = defaultdict(lambda: {"total": 0, "processed": 0, "results": []})
_progress_lock = threading.Lock()

_session_cache = {
    "csrf": None,
    "track": None,
    "session": None,
    "created": 0,
    "used": 0,
    "max_uses": 10,
    "ttl": 300  
}
_cache_lock = threading.Lock()

_phone_result_cache = {}  
_phone_result_cache_lock = threading.Lock()
_PHONE_CACHE_TTL = 3600 

_request_delay = 0.2

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

_phone_queue = defaultdict(list)
_check_active = defaultdict(bool)

_tesseract_path = None

_stats_file = "stats.json"
_stats = {
    "users": set(),
    "total_requests": 0,
    "daily_requests": 0,
    "last_reset_date": datetime.now().strftime("%Y-%m-%d")
}
_trusted_users = set()

_admin_id = os.environ.get("BOT_ADMIN_ID")
if _admin_id:
    _trusted_users.add(_admin_id)

_session_pool = threading.local()

_easyocr_reader = None
_easyocr_lock = threading.Lock()


def get_session():
    """Получение сессии из пула с настройками retry и таймаутами"""
    if not hasattr(_session_pool, 'session') or _session_pool.session is None:
        session = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        _session_pool.session = session
    return _session_pool.session


def get_cached_csrf_track():
    """
    Получение кешированной пары CSRF + track (на 10 номеров)
    """
    global _session_cache

    with _cache_lock:
        now = time.time()

        # Проверяем актуальность кеша
        if (_session_cache["csrf"] and
            _session_cache["track"] and
            _session_cache["session"] and
            _session_cache["used"] < _session_cache["max_uses"] and
            now - _session_cache["created"] < _session_cache["ttl"]):

            _session_cache["used"] += 1
            print(f"📦 Кеш: используем CSRF+track (# {_session_cache['used']}/{_session_cache['max_uses']})")
            return (
                _session_cache["csrf"],
                _session_cache["track"],
                _session_cache["session"]
            )

    # Кеш устарел или пуст — создаём новый
    print("🔄 Создаём новую сессию CSRF+track...")
    session = get_session()
    csrf_token = get_csrf_token_with_session(session)

    if not csrf_token:
        print("❌ Не удалось получить CSRF для кеша")
        return None, None, None

    track_id = create_track(csrf_token, session)

    if not track_id:
        print("❌ Не удалось создать track для кеша")
        return None, None, None

    # Сохраняем в кеш
    with _cache_lock:
        _session_cache.update({
            "csrf": csrf_token,
            "track": track_id,
            "session": session,
            "created": now,
            "used": 1
        })

    print(f"✅ Новая сессия: CSRF={csrf_token[:20]}..., track={track_id}")
    return csrf_token, track_id, session


def get_csrf_token_with_session(session):
    """Получение CSRF токена с использованием переданной сессии"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    }

    try:
        response = session.get('https://passport.yandex.ru/auth/', headers=headers, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None

    if response.status_code != 200:
        print(f"❌ Статус ответа: {response.status_code}")
        return None

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
            return csrf

    for cookie in session.cookies:
        if 'csrf' in cookie.name.lower() or cookie.name == 'yc':
            return cookie.value

    print("❌ CSRF не найден")
    return None


def get_easyocr_reader():
    """Получение закешированного EasyOCR reader"""
    global _easyocr_reader
    with _easyocr_lock:
        if _easyocr_reader is None:
            print("🔄 Инициализация EasyOCR reader (первый запуск)...")
            _easyocr_reader = easyocr.Reader(['en'], gpu=True, verbose=False)
            print("✅ EasyOCR reader инициализирован")
        return _easyocr_reader


def solve_captcha_hybrid(image_url):
    """
    Распознавание капчи (только EasyOCR)
    """
    return solve_captcha_easyocr(image_url)


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

        session = get_session()
        img_response = session.get(image_url, timeout=10)
        if img_response.status_code != 200:
            print(f"❌ Не удалось скачать изображение: {img_response.status_code}")
            return None

        img = Image.open(io.BytesIO(img_response.content))

        reader = get_easyocr_reader()
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
    session = get_session()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    }

    try:
        response = session.get('https://passport.yandex.ru/auth/', headers=headers, timeout=10)
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

    response = session.get('https://passport.yandex.ru/auth/', headers=fresh_headers, timeout=10)

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
        response = session.post(url, headers=headers, json=data, timeout=15)
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
        response = session.post(url, headers=headers, json=data, timeout=15)

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
        check_response = session.post(captcha_check_url, headers=captcha_headers, json=captcha_data, timeout=15)
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
        response = session.post(url, headers=headers, json=data, timeout=15)
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
    Максимум 5 попыток, потом смена track
    """
    attempt = 0
    max_attempts = 5

    while True:
        attempt += 1
        print(f"\n🔄 Попытка решения капчи #{attempt} (макс. {max_attempts})")

        # Проверяем флаг пропуска
        if chat_id and get_skip_flag(chat_id):
            print("⚠️ Получена команда /skip, завершение цикла")
            clear_skip_flag(chat_id)
            return None

        # Лимит попыток
        if attempt > max_attempts:
            print(f"⚠️ Превышен лимит попыток ({max_attempts}), создаём новый track...")
            # Создаём новый track с теми же CSRF и session
            new_track = create_track(csrf_token, session)
            if new_track:
                track_id = new_track
                attempt = 0
                print(f"✅ Новый track: {track_id}")
                continue
            else:
                print("❌ Не удалось создать новый track")
                return None

        captcha_data = generate_captcha(csrf_token, session, track_id)

        if not captcha_data:
            print("❌ Не удалось получить капчу, повторная попытка...")
            time.sleep(2)
            continue

        print(f"✅ Капча получена, key: {captcha_data.get('key', 'unknown')[:20]}...")

        answer = None

        if 'image_url' in captcha_data:
            # Используем гибридное распознавание
            answer = solve_captcha_hybrid(captcha_data['image_url'])

            if not answer:
                print("❌ Не удалось распознать капчу, повторная попытка...")
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
            time.sleep(1)  # Небольшая задержка перед следующей капчей
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

    # Проверяем кеш результатов
    with _phone_result_cache_lock:
        cached = _phone_result_cache.get(phone)
        if cached and time.time() - cached["time"] < _PHONE_CACHE_TTL:
            print(f"📦 Кеш результата: {phone} -> {cached['result']}")
            return cached["result"]

    # Ограничение одновременных проверок
    acquired = _check_semaphore.acquire(timeout=120)
    if not acquired:
        print("⚠️ Превышено время ожидания в очереди")
        return None

    try:
        # Создаём новую сессию CSRF+track для каждого номера
        session = get_session()
        csrf_token = get_csrf_token_with_session(session)
        if not csrf_token:
            csrf_token, session = get_csrf_token()
        if not csrf_token:
            print("❌ CSRF не получен")
            return None
        track_id = create_track(csrf_token, session)
        if not track_id:
            print("❌ Не удалось создать трек")
            return None

        print(f"✅ Используем трек: {track_id}")

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
                        res = "registered" if has_available else "not_registered"
                        with _phone_result_cache_lock:
                            _phone_result_cache[phone] = {"result": res, "time": time.time()}
                        return res
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
                res = "registered" if has_available else "not_registered"
                with _phone_result_cache_lock:
                    _phone_result_cache[phone] = {"result": res, "time": time.time()}
                return res
        else:
            print("❌ check_availability вернул None")

        return None
    finally:
        _check_semaphore.release()


def process_phone_result(phone, result, chat_id):
    """Форматирование и отправка результата проверки"""
    if result == "registered":
        response = f"✅ Аккаунт зарегистрирован"
    elif result == "not_registered":
        response = f"❌ Аккаунт не зарегистрирован"
    elif result is None:
        response = f"⚠️ Проверка пропущена по команде /skip или ошибка"
    else:
        response = f"❌ Не удалось проверить номер"

    return response


def process_queue(chat_id):
    """Обработка очереди номеров для чата - все номера параллельно, один итоговый файл"""
    global _check_active, _check_progress
    
    # Если уже идёт проверка - выходим
    if _check_active[chat_id]:
        return
    
    _check_active[chat_id] = True
    
    # Копируем очередь и очищаем её
    phones_to_check = list(_phone_queue[chat_id])
    _phone_queue[chat_id] = []

    # Находим и удаляем дубликаты
    seen = []
    duplicates = []
    for phone in phones_to_check:
        if phone in seen:
            if phone not in duplicates:
                duplicates.append(phone)
        else:
            seen.append(phone)
    phones_to_check = seen

    if duplicates:
        dup_text = "\n".join(f"  • {p}" for p in duplicates)
        bot.send_message(chat_id, f"⚠️ Найдены дубликаты ({len(duplicates)} шт.) — исключены из проверки:\n{dup_text}")

    total = len(phones_to_check)

    # Инициализируем прогресс
    with _progress_lock:
        _check_progress[chat_id] = {
            "total": total,
            "processed": 0,
            "results": [],
            "errors": [],
            "started": time.time()
        }

    # Отправляем уведомление о начале
    if total > 10:
        bot.send_message(chat_id, f"🔄 Начата проверка {total} номеров...\n\n⏳ Ожидаемое время: ~{max(30, total // 2)} сек.\n\nИспользуйте /status для просмотра прогресса")
    
    results = []
    
    def check_single_phone(phone):
        """Проверка одного номера с обновлением прогресса"""
        result = check_phone(phone, chat_id=None)  # Не считаем запросы повторно
        
        if result == "registered":
            status = "✅"
            detail = "зарегистрирован"
        elif result == "not_registered":
            status = "❌"
            detail = "не зарегистрирован"
        else:
            status = "⚠️"
            detail = "ошибка проверки"
        
        with _progress_lock:
            _check_progress[chat_id]["processed"] += 1
            result_entry = f"{status} {phone}"
            _check_progress[chat_id]["results"].append(result_entry)
            
            # Сохраняем детали ошибок
            if result is None:
                _check_progress[chat_id]["errors"].append(f"{phone} — ошибка проверки (таймаут/капча/сеть)")
        
        return (phone, result)
    
    # Запускаем все номера параллельно
    futures = []
    for phone in phones_to_check:
        future = _executor.submit(check_single_phone, phone)
        futures.append(future)
    
    # Ждём завершения всех проверок
    for future in futures:
        try:
            future.result(timeout=180)
        except Exception as e:
            print(f"❌ Ошибка при проверке: {e}")
    
    # Собираем результаты
    with _progress_lock:
        results = _check_progress[chat_id]["results"].copy()
        errors_list = _check_progress[chat_id]["errors"].copy()
        elapsed = time.time() - _check_progress[chat_id]["started"]
        del _check_progress[chat_id]
    
    # Формируем итоговый отчёт
    registered = sum(1 for r in results if r.startswith("✅"))
    not_registered = sum(1 for r in results if r.startswith("❌"))
    errors = sum(1 for r in results if r.startswith("⚠️"))
    
    # Создаём итоговое сообщение
    summary = (
        f"📊 **Итоги проверки**\n\n"
        f"⏱ Время: {elapsed:.1f} сек.\n"
        f"📱 Всего номеров: {total}\n"
        f"✅ Зарегистрировано: {registered}\n"
        f"❌ Не зарегистрировано: {not_registered}\n"
        f"⚠️ Ошибок: {errors}\n\n"
    )
    
    # Добавляем детали ошибок если есть
    if errors > 0:
        summary += f"🔴 **Номера с ошибками ({len(errors_list)}):**\n"
        for err in errors_list[:10]:  # Показываем первые 10
            summary += f"  • {err}\n"
        if len(errors_list) > 10:
            summary += f"  ... и ещё {len(errors_list) - 10}\n"
        summary += "\n"
    
    # Если номеров много - сохраняем в файл
    if total >= 20:
        # Создаём временный файл с результатами
        filename = f"result_{chat_id}_{int(time.time())}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(summary.replace("**", ""))
            f.write("\n" + "="*50 + "\n\n")
            for result in results:
                f.write(result + "\n")
        
        # Отправляем файл
        try:
            with open(filename, 'rb') as f:
                bot.send_document(chat_id, f, caption=summary, parse_mode="Markdown")
            os.remove(filename)
        except Exception as e:
            print(f"❌ Ошибка отправки файла: {e}")
            # Фолбэк - отправляем текстом
            bot.send_message(chat_id, summary + "\n".join(results[:50]) + ("\n... и ещё" if len(results) > 50 else ""))
    else:
        # Отправляем текстом
        full_report = summary + "\n".join(results)
        bot.send_message(chat_id, full_report, parse_mode="Markdown")
    
    _check_active[chat_id] = False


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 
        "👋 Привет! Отправь мне номер телефона для проверки.\n\n"
        "📋 **Команды:**\n"
        "/start - Это сообщение\n"
        "/status - Прогресс текущей проверки\n"
        "/skip - Пропустить капчу\n"
        "/id - Узнать chat_id\n"
        "/stats - Статистика бота (для админов)\n\n"
        "📱 **Формат номера:**\n"
        "89212810954 или +79212810954\n\n"
        "📬 **Можно отправлять:**\n"
        "- По одному в сообщении\n"
        "- До 100 номеров сразу (каждый с новой строки)\n\n"
        "⚡ **Оптимизации:**\n"
        "- 100 номеров за 60-90 сек\n"
        "- Гибридное распознавание капч (Tesseract + EasyOCR)\n"
        "- Кеширование сессий\n"
        "- Результат одним файлом")


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


@bot.message_handler(commands=['status'])
def show_status(message):
    chat_id = message.chat.id
    
    with _progress_lock:
        if chat_id not in _check_progress:
            bot.reply_to(message, "ℹ️ Нет активных проверок в этом чате")
            return
        
        progress = _check_progress[chat_id]
        total = progress["total"]
        processed = progress["processed"]
        percent = (processed / total * 100) if total > 0 else 0
        elapsed = time.time() - progress.get("started", time.time())
        
        # Оценка оставшегося времени
        if processed > 0 and elapsed > 0:
            avg_per_number = elapsed / processed
            remaining = (total - processed) * avg_per_number
            eta = f"~{remaining:.0f} сек."
        else:
            eta = "вычисление..."
        
        status_text = (
            f"📊 **Прогресс проверки**\n\n"
            f"📱 Всего номеров: {total}\n"
            f"✅ Обработано: {processed}/{total}\n"
            f"📈 Прогресс: {percent:.1f}%\n"
            f"⏱ Прошло времени: {elapsed:.1f} сек.\n"
            f"⏳ Осталось: {eta}\n\n"
            f"🔄 Пожалуйста, дождитесь завершения..."
        )
        
        bot.reply_to(message, status_text, parse_mode="Markdown")


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

    # Подсчёт запросов для статистики
    if chat_id:
        for _ in valid_phones:
            add_user_request(chat_id)

    # Добавляем номера в очередь
    _phone_queue[chat_id].extend(valid_phones)

    if len(valid_phones) == 1 and not _check_active[chat_id]:
        # Один номер - быстрая проверка
        phone = valid_phones[0]
        bot.reply_to(message, f"🔍 Проверяю номер {phone}...")
        
        future = _executor.submit(check_phone, phone, chat_id=None)
        try:
            result = future.result(timeout=180)
        except Exception as e:
            print(f"❌ Ошибка при проверке {phone}: {e}")
            result = None
        
        status = "✅" if result == "registered" else ("❌" if result == "not_registered" else "⚠️")
        bot.send_message(chat_id, f"{phone}: {status}")
    else:
        # Несколько номеров или активная проверка - в очередь
        total_queued = len(_phone_queue[chat_id])
        bot.reply_to(message, f"🔍 Добавлено номеров: {len(valid_phones)}\n📋 В очереди: {total_queued}\n\nНачинаю проверку...")

        # Запускаем обработку очереди в пуле потоков
        _executor.submit(process_queue, chat_id)


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

    # Предварительная инициализация EasyOCR
    print("\n🔄 Предварительная инициализация EasyOCR...")
    get_easyocr_reader()

    print("\n🤖 Бот запущен (многопоточный режим, макс. одновременных проверок: {})...".format(MAX_CONCURRENT_CHECKS))
    try:
        bot.infinity_polling(skip_pending=True, timeout=60)
    except KeyboardInterrupt:
        print("\n🛑 Остановка бота...")
    finally:
        print("🔄 Завершение пула потоков...")
        _executor.shutdown(wait=False)
