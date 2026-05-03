"""
Примеры использования REST API сервера
"""

import requests
import time
import json

BASE_URL = "http://localhost:8000"

def example_1_check_single_phone():
    """Пример 1: Проверить один номер"""
    print("\n" + "="*50)
    print("ПРИМЕР 1: Проверка одного номера")
    print("="*50)

    response = requests.post(
        f"{BASE_URL}/api/check/phone",
        json={"phone": "89212810954"}
    )

    print(f"Status: {response.status_code}")
    print(f"Result: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")


def example_2_check_batch():
    """Пример 2: Проверить несколько номеров асинхронно"""
    print("\n" + "="*50)
    print("ПРИМЕР 2: Проверка нескольких номеров (асинхронно)")
    print("="*50)

    # Запускаем проверку
    response = requests.post(
        f"{BASE_URL}/api/check/batch",
        json={
            "phones": [
                "89212810954",
                "89213456789",
                "89999999999"
            ],
            "max_concurrent": 15
        }
    )

    task_id = response.json()["task_id"]
    print(f"Task ID: {task_id}")
    print(f"Message: {response.json()['message']}")

    # Ждём завершения и проверяем статус
    print("\nОтслеживание прогресса:")
    while True:
        status = requests.get(f"{BASE_URL}/api/status/{task_id}")
        data = status.json()

        print(f"  Progress: {data['processed']}/{data['total']} ({data['percent']:.1f}%) | Elapsed: {data['elapsed_seconds']:.1f}s", end="\r")

        if data["status"] != "processing":
            break

        time.sleep(1)

    print("\n✅ Проверка завершена!")

    # Получаем результаты
    results = requests.get(f"{BASE_URL}/api/results/{task_id}")
    data = results.json()

    print(f"\nРезультаты:")
    print(f"  Зарегистрировано: {data['summary']['registered']}")
    print(f"  Не зарегистрировано: {data['summary']['not_registered']}")
    print(f"  Ошибок: {data['summary']['errors']}")
    print(f"  Время выполнения: {data['summary']['elapsed_seconds']:.1f}s")


def example_3_health_check():
    """Пример 3: Проверка здоровья сервера"""
    print("\n" + "="*50)
    print("ПРИМЕР 3: Проверка здоровья сервера")
    print("="*50)

    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Result: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")


def example_4_server_info():
    """Пример 4: Информация о сервере"""
    print("\n" + "="*50)
    print("ПРИМЕР 4: Информация о сервере")
    print("="*50)

    response = requests.get(f"{BASE_URL}/")
    data = response.json()

    print(f"Name: {data['name']}")
    print(f"Status: {data['status']}")
    print(f"Version: {data['version']}")
    print(f"\nEndpoints:")
    for name, endpoint in data['endpoints'].items():
        print(f"  {name}: {endpoint}")


def example_5_stats():
    """Пример 5: Получить статистику"""
    print("\n" + "="*50)
    print("ПРИМЕР 5: Статистика сервера")
    print("="*50)

    response = requests.get(f"{BASE_URL}/api/stats")
    data = response.json()

    print(f"Всего пользователей: {data['total_users']}")
    print(f"Всего запросов: {data['total_requests']}")
    print(f"Запросов сегодня: {data['daily_requests']}")
    print(f"Активных задач: {data['active_tasks']}")
    print(f"Последний сброс: {data['last_reset_date']}")


def example_6_batch_with_polling():
    """Пример 6: Batch проверка с регулярным опросом статуса"""
    print("\n" + "="*50)
    print("ПРИМЕР 6: Batch с регулярным опросом")
    print("="*50)

    phones = [
        "89212810954",
        "89213456789",
        "89999999999",
        "89123456789",
        "89987654321"
    ]

    # Запускаем
    response = requests.post(
        f"{BASE_URL}/api/check/batch",
        json={"phones": phones, "max_concurrent": 10}
    )

    task_id = response.json()["task_id"]
    print(f"Запущена проверка {len(phones)} номеров")
    print(f"Task ID: {task_id}")

    # Проверяем статус каждые 2 секунды
    print("\nПрогресс:")
    start = time.time()
    while True:
        status = requests.get(f"{BASE_URL}/api/status/{task_id}")
        data = status.json()

        elapsed = data['elapsed_seconds']
        percent = data['percent']
        processed = data['processed']
        total = data['total']

        # Простой прогресс бар
        filled = int(percent / 5)
        bar = "█" * filled + "░" * (20 - filled)

        print(f"[{bar}] {percent:.0f}% ({processed}/{total}) | {elapsed:.1f}s", end="\r")

        if data["status"] != "processing":
            break

        time.sleep(2)

    print(f"\n✅ Завершено за {time.time() - start:.1f}s")

    # Итоги
    results = requests.get(f"{BASE_URL}/api/results/{task_id}")
    summary = results.json()['summary']

    print(f"\nИтоги:")
    print(f"  ✅ Зарегистрировано: {summary['registered']}")
    print(f"  ❌ Не зарегистрировано: {summary['not_registered']}")
    print(f"  ⚠️ Ошибок: {summary['errors']}")


if __name__ == "__main__":
    print("\n🚀 Примеры использования Yandex Phone Checker API")
    print("\nУбедитесь, что сервер запущен: python server.py")

    try:
        # Проверяем подключение
        requests.get(f"{BASE_URL}/health", timeout=2)
    except Exception as e:
        print(f"\n❌ Ошибка подключения к серверу: {e}")
        print(f"Запустите сервер: python server.py")
        exit(1)

    print("\n" + "="*50)
    print("Выберите пример для запуска:")
    print("="*50)
    print("1. Проверка одного номера (синхронно)")
    print("2. Проверка нескольких номеров (асинхронно)")
    print("3. Проверка здоровья сервера")
    print("4. Информация о сервере")
    print("5. Статистика")
    print("6. Batch с регулярным опросом")
    print("0. Запустить все примеры")

    choice = input("\nВаш выбор: ").strip()

    if choice == "0":
        try:
            example_1_check_single_phone()
            example_3_health_check()
            example_4_server_info()
            example_5_stats()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    elif choice == "1":
        try:
            example_1_check_single_phone()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    elif choice == "2":
        try:
            example_2_check_batch()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    elif choice == "3":
        try:
            example_3_health_check()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    elif choice == "4":
        try:
            example_4_server_info()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    elif choice == "5":
        try:
            example_5_stats()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    elif choice == "6":
        try:
            example_6_batch_with_polling()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    else:
        print("❌ Неверный выбор")
