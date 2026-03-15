"""
Скрипт для подбора оптимальных параметров EasyOCR для капч Яндекса
Проверяет номера через Яндекс API и тестирует разные параметры OCR
"""

import requests
import re
import uuid
import json
import time
import easyocr
from PIL import Image
import io
import numpy as np
from itertools import product
import os

# Файл с номерами (каждый номер с новой строки)
PHONES_FILE = "phones_for_test.txt"

# Параметры для тестирования (3×3×3 = 27 комбинаций)
PARAM_GRID = {
    'text_threshold': [0.5, 0.6, 0.7],
    'low_text': [0.3, 0.4, 0.5],
    'mag_ratio': [1.0, 1.3, 1.5],
}


def format_phone_number(phone):
    """Преобразование номера в формат +7 XXX XXX-XX-XX"""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    elif len(digits) == 10:
        digits = '7' + digits
    if len(digits) != 11 or not digits.startswith('7'):
        return None
    return f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"


def get_csrf_token():
    """Получение CSRF-токена"""
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
        (r'"csrfToken"\s*:\s*"([^"]+)"', "JSON csrfToken"),
    ]
    for pattern, _ in patterns:
        match = re.search(pattern, response.text, re.IGNORECASE)
        if match:
            return match.group(1), session

    for cookie in session.cookies:
        if 'csrf' in cookie.name.lower():
            return cookie.value, session

    return None, session


def get_csrf_with_fresh_headers(session):
    """Получение CSRF со свежими заголовками"""
    headers = {
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
    response = session.get('https://passport.yandex.ru/auth/', headers=headers)
    if response.status_code == 200:
        match = re.search(r'window\.__CSRF__\s*=\s*"([^"]+)"', response.text)
        if match:
            return match.group(1)
    return None


def create_track(csrf_token, session):
    """Создание трека"""
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
        print(f"Ошибка create_track: {e}")
    return None


def generate_captcha(csrf_token, session, track_id):
    """Генерация капчи"""
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
            return response.json()
    except:
        pass
    return None


def check_availability(csrf_token, session, track_id, phone_number):
    """Проверка доступности номера"""
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
    except Exception as e:
        print(f"Ошибка check_availability: {e}")
    return None


def submit_captcha_and_recheck(csrf_token, session, track_id, phone_number, captcha_key, captcha_answer):
    """Отправка капчи и повторная проверка"""
    url = "https://passport.yandex.ru/pwl-yandex/api/passport/captcha/check"
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
        "answer": captcha_answer,
        "key": captcha_key,
        "track_id": track_id
    }
    try:
        response = session.post(url, headers=headers, json=data)
        if response.status_code == 200:
            result = response.json()
            if not result.get('correct', False):
                return None
    except:
        return None

    time.sleep(0.5)
    return check_availability(csrf_token, session, track_id, phone_number)


def solve_captcha_with_params(image_url, params):
    """Распознавание капчи с заданными параметрами"""
    try:
        img_response = requests.get(image_url, stream=True)
        if img_response.status_code != 200:
            return None

        img = Image.open(io.BytesIO(img_response.content))
        img_array = np.array(img)

        # Инициализируем EasyOCR (GPU для скорости)
        reader = easyocr.Reader(['en'], gpu=True, verbose=False)
        results = reader.readtext(img_array, **params)

        sorted_results = sorted(results, key=lambda x: x[0][0][0])
        texts = [res[1].lower() for res in sorted_results]
        full_text = ' '.join(texts)
        clean_text = re.sub(r'[^a-z\s]', '', full_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        return clean_text if clean_text else None

    except Exception as e:
        return None


def clean_captcha_text(text):
    """Умная очистка для капч Яндекса"""
    text = text.lower()
    replacements = {
        'о': 'o', 'а': 'a', 'е': 'e', 'х': 'x', 'с': 'c', 'у': 'y',
        'р': 'p', 'в': 'b', 'к': 'k', 'м': 'm', 'т': 't', 'н': 'h',
        '1': 'l', '0': 'o', '6': 'g', '8': 'b', '9': 'g', '5': 's',
        '2': 'z', '7': 't', '4': 'h', 'i': 'l', 'q': 'o', 'd': 'cl',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'[^a-z]', '', text)
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)
    return text.strip()


def load_phones(filename):
    """Загрузка номеров из файла"""
    if not os.path.exists(filename):
        return None
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    phones = []
    for line in lines:
        line = line.strip()
        if line:
            formatted = format_phone_number(line)
            if formatted:
                phones.append(formatted)
    return phones


def main():
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  EasyOCR Parameter Tuner + Yandex Phone Checker           ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()

    # Загрузка номеров
    print(f"📂 Загрузка номеров из {PHONES_FILE}...")
    phones = load_phones(PHONES_FILE)

    if not phones:
        print(f"❌ Не удалось загрузить номера")
        print(f"Создайте файл {PHONES_FILE} и поместите в него номера")
        return

    print(f"✅ Загружено номеров: {len(phones)}")
    print()

    # Генерация комбинаций параметров
    all_combinations = list(product(
        PARAM_GRID['text_threshold'],
        PARAM_GRID['low_text'],
        PARAM_GRID['mag_ratio']
    ))

    test_params_list = []
    for tt, lt, mr in all_combinations:
        test_params_list.append({
            'text_threshold': tt,
            'low_text': lt,
            'mag_ratio': mr,
            'batch_size': 1,
            'paragraph': False,
        })

    print(f"📊 Комбинаций параметров для теста: {len(test_params_list)}")
    print()

    # Статистика по параметрам
    param_stats = {i: {
        'tested': 0,
        'success': 0,
        'total_length': 0,
    } for i in range(len(test_params_list))}

    # Проверка номеров
    print("=" * 70)
    print(f"ПРОВЕРКА {len(phones)} НОМЕРОВ")
    print("=" * 70)
    print()

    total_captchas = 0
    captcha_limit = 20  # Останавливаемся после 20 капч
    start_time = time.time()

    # CSRF и трек (как в main.py)
    csrf_token, session = get_csrf_token()
    if not csrf_token:
        csrf_token = get_csrf_with_fresh_headers(session)

    if not csrf_token:
        print("❌ Не удалось получить CSRF-токен")
        return

    track_id = create_track(csrf_token, session)
    if not track_id:
        print("❌ Не удалось создать трек")
        return

    for i, phone in enumerate(phones, 1):
        print(f"[{i}/{len(phones)}] {phone}", end=" ... ")

        # Проверка номера
        result = check_availability(csrf_token, session, track_id, phone)

        if not result:
            print("❌ Ошибка")
            # Пробуем новый трек
            track_id = create_track(csrf_token, session)
            if not track_id:
                print("❌ Не удалось создать новый трек")
                break
            continue

        # Если нет капчи
        if result.get('antifraudScore') != 'captcha':
            has_available = result.get('hasAvailableAccounts', False)
            status = "✅" if has_available else "❌"
            print(f"{status} {'registered' if has_available else 'not_registered'}")

            # Новый трек для следующего номера
            track_id = create_track(csrf_token, session)
            if not track_id:
                print("⚠️ Не удалось создать новый трек, продолжаем...")
            continue

        # Нужна капча
        print("⚠️ captcha", end=" ... ")

        captcha_data = generate_captcha(csrf_token, session, track_id)
        if not captcha_data or 'image_url' not in captcha_data:
            print("❌ Не удалось получить капчу")
            track_id = create_track(csrf_token, session)
            continue

        captcha_url = captcha_data['image_url']
        captcha_key = captcha_data.get('key')
        total_captchas += 1

        # Тестируем все параметры на этой капче
        print("🔍 Тест параметров...", end=" ")
        captcha_results = {}
        for param_idx, params in enumerate(test_params_list):
            answer = solve_captcha_with_params(captcha_url, params)
            if answer:
                answer = clean_captcha_text(answer)
            captcha_results[param_idx] = answer
            print(f"#{param_idx+1}:{len(answer) if answer else 0}", end=" ")
        print()

        # Отправляем первый ответ (с дефолтными параметрами)
        first_answer = captcha_results.get(0)

        if not first_answer or len(first_answer) < 4:
            print("❌ Не распознана")
            track_id = create_track(csrf_token, session)
            continue

        # Проверяем капчу
        check_result = submit_captcha_and_recheck(
            csrf_token, session, track_id, phone,
            captcha_key, first_answer
        )

        if not check_result or not check_result.get('correct'):
            print("❌ Капча неверная")
            track_id = create_track(csrf_token, session)
            continue

        # Успешная капча - обновляем статистику
        print("✅ решена", end="")

        for param_idx, answer in captcha_results.items():
            if answer and len(answer) >= 4:
                param_stats[param_idx]['tested'] += 1
                param_stats[param_idx]['success'] += 1
                param_stats[param_idx]['total_length'] += len(answer)
            elif answer:
                param_stats[param_idx]['tested'] += 1

        # Повторная проверка
        final_result = check_availability(csrf_token, session, track_id, phone)
        if final_result:
            has_available = final_result.get('hasAvailableAccounts', False)
            status = "✅" if has_available else "❌"
            print(f" -> {status} {'registered' if has_available else 'not_registered'}")
        else:
            print()

        # Новый трек
        track_id = create_track(csrf_token, session)

        # Лимит капч
        if total_captchas >= captcha_limit:
            print()
            print(f"⏹ Достигнут лимит капч для теста ({captcha_limit})")
            break

        # Промежуточные итоги каждые 5 капч
        if total_captchas % 5 == 0:
            print(f"📊 Прогресс: {total_captchas}/{captcha_limit} капч")
            print()

    elapsed = time.time() - start_time

    print()
    print("=" * 70)
    print("СТАТИСТИКА ПАРАМЕТРОВ")
    print("=" * 70)
    print()

    # Вычисляем средние
    for param_idx in param_stats:
        stats = param_stats[param_idx]
        if stats['success'] > 0:
            stats['avg_length'] = stats['total_length'] / stats['success']
        else:
            stats['avg_length'] = 0
        stats['success_rate'] = (stats['success'] / stats['tested'] * 100) if stats['tested'] > 0 else 0
        stats['score'] = stats['success_rate'] * stats['avg_length'] / 10 if stats['avg_length'] > 0 else 0

    # Сортируем по score
    sorted_params = sorted(
        param_stats.items(),
        key=lambda x: x[1]['score'],
        reverse=True
    )

    print("ТОП-5 КОМБИНАЦИЙ:")
    print()

    for rank, (param_idx, stats) in enumerate(sorted_params[:5], 1):
        params = test_params_list[param_idx]
        print(f"{rank}. text_threshold={params['text_threshold']}, "
              f"low_text={params['low_text']}, mag_ratio={params['mag_ratio']}")
        print(f"   Тестировано: {stats['tested']} капч")
        print(f"   Успешно: {stats['success']} ({stats['success_rate']:.0f}%)")
        print(f"   Ср. длина: {stats['avg_length']:.1f} симв.")
        print(f"   Score: {stats['score']:.2f}")
        print()

    if sorted_params and sorted_params[0][1]['tested'] > 0:
        best_idx, best_stats = sorted_params[0]
        best_params = test_params_list[best_idx]

        print("=" * 70)
        print("ЛУЧШИЕ ПАРАМЕТРЫ (скопируйте в bot.py):")
        print("=" * 70)
        print()
        print("Откройте bot.py и найдите:")
        print("  results = reader.readtext(img_array, ...)")
        print()
        print("Замените на:")
        print()
        print(f"  results = reader.readtext(")
        print(f"      img_array,")
        print(f"      text_threshold={best_params['text_threshold']},")
        print(f"      low_text={best_params['low_text']},")
        print(f"      mag_ratio={best_params['mag_ratio']},")
        print(f"      batch_size=1,")
        print(f"      paragraph=False")
        print(f"  )")
        print()
        print(f"Ожидаемая точность: {best_stats['success_rate']:.0f}%")
        print(f"Ожидаемая длина: {best_stats['avg_length']:.1f} симв.")
        print()
    else:
        print("=" * 70)
        print("НЕДОСТАТОЧНО ДАННЫХ")
        print("=" * 70)
        print("Нужно минимум 5 успешных капч для анализа")
        print()

    print("=" * 70)
    print(f"Время проверки: {elapsed:.1f} сек.")
    print(f"Всего капч: {total_captchas}")
    print("=" * 70)
    print()
    print("Готово!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
