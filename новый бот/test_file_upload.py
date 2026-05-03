"""
Скрипт для тестирования загрузки файлов в API
"""

import requests
import time
import os

BASE_URL = "http://localhost:8000"

# Создаём тестовый TXT файл
def create_test_txt():
    with open("test_phones.txt", "w", encoding="utf-8") as f:
        f.write("""89212810954
+79213456789
89999999999
89123456789
89987654321
""")
    print("✅ Создан test_phones.txt")
    return "test_phones.txt"

# Создаём тестовый CSV файл
def create_test_csv():
    with open("test_phones.csv", "w", encoding="utf-8") as f:
        f.write("""phone
89212810954
79213456789
89999999999
89123456789
89987654321
""")
    print("✅ Создан test_phones.csv")
    return "test_phones.csv"

# Тестируем загрузку файла
def test_file_upload(filename):
    print(f"\n{'='*50}")
    print(f"Тестирование: {filename}")
    print('='*50)

    if not os.path.exists(filename):
        print(f"❌ Файл {filename} не найден")
        return

    try:
        # Загружаем файл
        with open(filename, "rb") as f:
            files = {"file": f}
            data = {"max_concurrent": 10}

            response = requests.post(
                f"{BASE_URL}/api/check/file",
                files=files,
                data=data
            )

        if response.status_code != 200:
            print(f"❌ Ошибка: {response.status_code}")
            print(response.json())
            return

        result = response.json()
        task_id = result["task_id"]

        print(f"📤 Загружено: {result['message']}")
        print(f"🆔 Task ID: {task_id}")
        print(f"📊 Status: {result['status']}")

        # Отслеживаем прогресс
        print(f"\n⏳ Отслеживание прогресса:")
        start_time = time.time()
        last_percent = 0

        while True:
            status = requests.get(f"{BASE_URL}/api/status/{task_id}")
            data = status.json()

            percent = data["percent"]
            processed = data["processed"]
            total = data["total"]
            elapsed = data["elapsed_seconds"]

            if percent != last_percent:
                # Простой прогресс бар
                filled = int(percent / 5)
                bar = "█" * filled + "░" * (20 - filled)
                print(f"[{bar}] {percent:.0f}% ({processed}/{total}) | {elapsed:.1f}s")
                last_percent = percent

            if data["status"] != "processing":
                break

            time.sleep(1)

        # Получаем результаты
        results = requests.get(f"{BASE_URL}/api/results/{task_id}")
        final_data = results.json()

        print(f"\n✅ Завершено за {time.time() - start_time:.1f}s")
        print(f"\n📊 Итоги:")
        print(f"  ✅ Зарегистрировано: {final_data['summary']['registered']}")
        print(f"  ❌ Не зарегистрировано: {final_data['summary']['not_registered']}")
        print(f"  ⚠️ Ошибок: {final_data['summary']['errors']}")
        print(f"  📱 Всего проверено: {final_data['summary']['processed']}")

        # Показываем первые результаты
        if final_data['results']:
            print(f"\n📋 Первые результаты:")
            for result in final_data['results'][:5]:
                status_icon = "✅" if result['status'] == "registered" else "❌" if result['status'] == "not_registered" else "⚠️"
                print(f"  {status_icon} {result['phone']}: {result['status']}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    print("\n🚀 Тестирование загрузки файлов")
    print(f"Сервер: {BASE_URL}\n")

    try:
        # Проверяем подключение
        requests.get(f"{BASE_URL}/health", timeout=2)
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print(f"Запустите сервер: python server.py")
        exit(1)

    # Создаём тестовые файлы
    txt_file = create_test_txt()
    csv_file = create_test_csv()

    # Тестируем оба формата
    test_file_upload(txt_file)
    test_file_upload(csv_file)

    print(f"\n{'='*50}")
    print("✅ Тестирование завершено!")
    print('='*50)
