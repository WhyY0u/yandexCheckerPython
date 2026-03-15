
import requests
import re
import uuid
import json
import time

import easyocr
from PIL import Image
import io


def solve_captcha_easyocr(image_url):
    try:
        img_response = requests.get(image_url, stream=True)
        if img_response.status_code != 200:
            return None

        img = Image.open(io.BytesIO(img_response.content))

        # Инициализируем EasyOCR (только английский, используем GPU)
        reader = easyocr.Reader(['en'], gpu=True, verbose=False)

        import numpy as np
        img_array = np.array(img)

        results = reader.readtext(img_array)

        sorted_results = sorted(results, key=lambda x: x[0][0][0])

        texts = [res[1].lower() for res in sorted_results]
        full_text = ' '.join(texts)

        clean_text = re.sub(r'[^a-z\s]', '', full_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        if clean_text:
            return clean_text

        return None

    except Exception as e:
        return None

def get_csrf_token():

    session = requests.Session()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    }

    response = session.get('https://passport.yandex.ru/auth/', headers=headers)

    if response.status_code != 200:
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
            return csrf, session

    for cookie in session.cookies:
        if 'csrf' in cookie.name.lower() or cookie.name == 'yc':
            return cookie.value, session

    return None, session

def get_csrf_with_fresh_headers(session):

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
        "country": "ru",
        "app_id": "",
        "app_version_name": "",
        "retpath": "",
        "device_id": "",
        "uid": "",
        "device_connection_type": ""
    }

    try:
        response = session.post(url, headers=headers, json=data)

        if response.status_code == 200:
            result = response.json()
            if 'id' in result:
                return result['id']
    except Exception as e:
        print(f"Ошибка при создании трека: {e}")

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
        check_response = session.post(captcha_check_url, headers=captcha_headers, json=captcha_data)
        
        if check_response.status_code == 200:
            captcha_result = check_response.json()
            if not captcha_result.get('correct', False):
                return None
        else:
            return None
    except Exception as e:
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

        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ Статус check_availability: {response.status_code}")
            print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"❌ Ошибка в check_availability: {e}")

    return None

def solve_captcha_loop(csrf_token, session, track_id, phone):
    """
    Цикл решения капч до получения hasAvailableAccounts (бесконечный цикл с повторными попытками)
    """
    attempt = 0

    while True:
        attempt += 1
        print(f"\n🔄 Попытка решения капчи #{attempt}")

        captcha_data = generate_captcha(csrf_token, session, track_id)

        if not captcha_data:
            print("❌ Не удалось получить капчу, повторная попытка через 2 секунды...")
            time.sleep(2)
            continue

        answer = None

        if 'image_url' in captcha_data:
            auto_answer = solve_captcha_easyocr(captcha_data['image_url'])

            if auto_answer:
                answer = auto_answer
            else:
                print("❌ Не удалось распознать капчу автоматически, повторная попытка через 2 секунды...")
                time.sleep(2)
                continue

        if not answer:
            print("❌ Нет ответа для капчи, повторная попытка через 2 секунды...")
            time.sleep(2)
            continue

        result = submit_captcha_and_recheck(csrf_token, session, track_id, phone,
                                            captcha_data['key'], answer)

        if not result:
            print("❌ Не удалось получить результат, повторная попытка через 2 секунды...")
            time.sleep(2)
            continue

        if 'hasAvailableAccounts' in result:
            return result

        if result.get('antifraudScore') == 'captcha':
            continue

        return result

def main():
    """
    Основная функция
    """
    csrf_token, session = get_csrf_token()
    if not csrf_token:
        csrf_token = get_csrf_with_fresh_headers(session)

    if not csrf_token:
        print("❌ Не удалось получить CSRF-токен")
        return

    print(f"✅ CSRF-ТОКЕН: {csrf_token}")

    track_id = create_track(csrf_token, session)
    if not track_id:
        print("❌ Не удалось создать трек")
        return

    print(f"✅ TRACK ID: {track_id}")

    phone = "+7 921 281-09-54"
    print(f"📞 Проверяем номер: {phone}")

    result = check_availability(csrf_token, session, track_id, phone)

    if result:
        if result.get('antifraudScore') == 'captcha':
            final_result = solve_captcha_loop(csrf_token, session, track_id, phone)
            
            if final_result:
                has_available = final_result.get('hasAvailableAccounts', False)
                if has_available:
                    print("✅ Аккаунт зарегистрирован")
                else:
                    print("❌ Аккаунт не зарегистрирован")
    else:
        print("❌ Не удалось получить результат проверки")

if __name__ == "__main__":
    main()