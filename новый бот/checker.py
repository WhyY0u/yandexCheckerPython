"""
Модуль для проверки доступности номеров в Yandex Passport
Используется как ботом, так и сервером
"""

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
    print("\n⚠️ Для работы необходимо установить Tesseract OCR:")
    print("\n1. Скачайте установщик:")
    print("   tesseract-ocr-w64-setup-5.5.0.20241111.exe")
    print("   https://github.com/UB-Mannheim/tesseract/wiki")
    print("\n2. Запустите установщик и следуйте инструкциям")
    print("   Путь по умолчанию: C:\\Program Files\\Tesseract-OCR")
    print("\n3. ⚠️ Обязательно отметьте галочку:")
    print("   ☑ Add Tesseract to the PATH")
    print("\n4. После установки перезапустите приложение")
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

        if chat_id and get_skip_flag(chat_id):
            print("⚠️ Получена команда /skip, завершение цикла")
            clear_skip_flag(chat_id)
            return None

        if attempt > max_attempts:
            print(f"⚠️ Превышен лимит попыток ({max_attempts}), создаём новый track...")
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
            time.sleep(1)
            continue

        return result


def check_phone(phone, chat_id=None, formatted_output=False):
    """
    Основная функция проверки номера
    """
    print(f"\n🔍 Начинаем проверку номера: {phone}")

    if chat_id:
        add_user_request(chat_id)

    with _phone_result_cache_lock:
        cached = _phone_result_cache.get(phone)
        if cached and time.time() - cached["time"] < _PHONE_CACHE_TTL:
            print(f"📦 Кеш результата: {phone} -> {cached['result']}")
            return cached["result"]

    acquired = _check_semaphore.acquire(timeout=120)
    if not acquired:
        print("⚠️ Превышено время ожидания в очереди")
        return None

    try:
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

        result = check_availability(csrf_token, session, track_id, phone)

        if result:
            print(f"📊 antifraudScore: {result.get('antifraudScore')}")

            if result.get('antifraudScore') == 'captcha':
                print("⚠️ Требуется капча, запускаем цикл решения...")
                while True:
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
                        if chat_id and get_skip_flag(chat_id):
                            clear_skip_flag(chat_id)
                            return None
                        print("⚠️ solve_captcha_loop вернул None, повторяем цикл...")
                        time.sleep(2)
            else:
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
