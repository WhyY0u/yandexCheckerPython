# Yandex Phone Checker CTF - REST API Server

REST API сервер для проверки доступности номеров телефонов в Yandex Passport.

## 🚀 Запуск

### 1. Установка зависимостей

```bash
pip install -r requirements_server.txt
```

### 2. Запуск сервера

```bash
python server.py
```

Сервер запустится на `http://localhost:8000`

## 📚 API Endpoints

### 1. Проверить один номер (синхронно)

**POST** `/api/check/phone`

Проверка одного номера телефона синхронно (ждёт результата).

**Request:**
```json
{
  "phone": "89212810954"
}
```

**Response:**
```json
{
  "phone": "+7 921 281-09-54",
  "status": "registered",
  "message": "✅ Номер зарегистрирован в Yandex",
  "timestamp": "2026-05-03T15:30:45.123456"
}
```

**Статусы:**
- `registered` - номер зарегистрирован
- `not_registered` - номер не зарегистрирован
- `error` - ошибка при проверке

### 2. Проверить несколько номеров (асинхронно)

**POST** `/api/check/batch`

Проверка нескольких номеров асинхронно. Возвращает `task_id` для отслеживания.

**Request:**
```json
{
  "phones": [
    "89212810954",
    "+79213456789",
    "89999999999"
  ],
  "max_concurrent": 15
}
```

**Response:**
```json
{
  "task_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "message": "Начата проверка 3 номеров",
  "status": "processing"
}
```

### 2.1 Загрузить файл с номерами

**POST** `/api/check/file`

Загрузка файла (TXT или CSV) с номерами телефонов. Один номер на строку.

**Поддерживаемые форматы:**

**TXT файл:**
```
89212810954
+79213456789
89999999999
```

**CSV файл:**
```
phone
89212810954
79213456789
89999999999
```

**Request (multipart/form-data):**
- `file` - файл (обязателен)
- `max_concurrent` - максимум одновременных проверок (опционально, по умолчанию 15)

**Response:**
```json
{
  "task_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "filename": "phones.txt",
  "message": "Загружено 1000 номеров из файла phones.txt",
  "status": "processing"
}
```

### 3. Получить статус проверки пакета

**GET** `/api/status/{task_id}`

Отслеживание прогресса проверки пакета номеров.

**Response:**
```json
{
  "task_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "processing",
  "total": 3,
  "processed": 2,
  "percent": 66.7,
  "results": [
    {
      "phone": "+7 921 281-09-54",
      "status": "registered",
      "checked_at": "2026-05-03T15:30:45.123456"
    }
  ],
  "elapsed_seconds": 5.2,
  "eta_seconds": 2.6,
  "started_at": "2026-05-03T15:30:40.123456",
  "completed_at": null
}
```

**Статусы задачи:**
- `processing` - идёт обработка
- `completed` - завершено
- `failed` - ошибка

### 4. Получить полные результаты проверки

**GET** `/api/results/{task_id}`

Получение всех результатов после завершения проверки.

**Response:**
```json
{
  "task_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "completed",
  "summary": {
    "total": 3,
    "processed": 3,
    "registered": 2,
    "not_registered": 1,
    "errors": 0,
    "elapsed_seconds": 8.5,
    "started_at": "2026-05-03T15:30:40.123456",
    "completed_at": "2026-05-03T15:30:48.123456"
  },
  "results": [
    {
      "phone": "+7 921 281-09-54",
      "status": "registered",
      "checked_at": "2026-05-03T15:30:45.123456"
    }
  ],
  "errors": []
}
```

### 5. Получить статистику

**GET** `/api/stats`

Получение общей статистики сервера.

**Response:**
```json
{
  "total_users": 42,
  "total_requests": 1234,
  "daily_requests": 56,
  "last_reset_date": "2026-05-03",
  "active_tasks": 3
}
```

### 6. Удалить задачу из памяти

**DELETE** `/api/tasks/{task_id}`

Удаление задачи из памяти сервера.

**Response:**
```json
{
  "message": "Задача f47ac10b-58cc-4372-a567-0e02b2c3d479 удалена"
}
```

### 7. Проверка здоровья сервера

**GET** `/health`

Простая проверка, что сервер работает.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-05-03T15:30:45.123456"
}
```

### 8. Информация о сервере

**GET** `/`

Получение информации о сервере и доступных endpoints.

**Response:**
```json
{
  "status": "online",
  "name": "Yandex Phone Checker Server",
  "version": "1.0.0",
  "endpoints": {
    "check_phone": "POST /api/check/phone",
    "check_batch": "POST /api/check/batch",
    "get_status": "GET /api/status/{task_id}",
    "get_results": "GET /api/results/{task_id}",
    "health": "GET /health"
  }
}
```

## 📌 Примеры использования

### Пример 1: Проверить один номер через curl

```bash
curl -X POST "http://localhost:8000/api/check/phone" \
  -H "Content-Type: application/json" \
  -d '{"phone": "89212810954"}'
```

### Пример 1.5: Загрузить файл через curl

**TXT файл:**
```bash
curl -X POST "http://localhost:8000/api/check/file" \
  -F "file=@phones.txt" \
  -F "max_concurrent=15"
```

**CSV файл:**
```bash
curl -X POST "http://localhost:8000/api/check/file" \
  -F "file=@phones.csv" \
  -F "max_concurrent=20"
```

### Пример 2: Проверить несколько номеров через Python

```python
import requests
import time

# Начинаем проверку
response = requests.post(
    "http://localhost:8000/api/check/batch",
    json={
        "phones": ["89212810954", "89213456789", "89999999999"],
        "max_concurrent": 15
    }
)

task_id = response.json()["task_id"]
print(f"Задача {task_id} создана")

# Проверяем статус в цикле
while True:
    status = requests.get(f"http://localhost:8000/api/status/{task_id}")
    data = status.json()
    
    print(f"Прогресс: {data['processed']}/{data['total']} ({data['percent']:.1f}%)")
    
    if data["status"] != "processing":
        break
    
    time.sleep(1)

# Получаем итоговые результаты
results = requests.get(f"http://localhost:8000/api/results/{task_id}")
print(results.json())
```

### Пример 3: Загрузить файл с номерами через Python

```python
import requests
import time

# Загружаем файл
with open("phones.txt", "rb") as f:
    files = {"file": f}
    data = {"max_concurrent": 15}
    
    response = requests.post(
        "http://localhost:8000/api/check/file",
        files=files,
        data=data
    )

task_data = response.json()
task_id = task_data["task_id"]
print(f"Загружено: {task_data['message']}")
print(f"Task ID: {task_id}")

# Ждём завершения
while True:
    status = requests.get(f"http://localhost:8000/api/status/{task_id}")
    data = status.json()
    
    print(f"Progress: {data['processed']}/{data['total']} ({data['percent']:.1f}%)")
    
    if data["status"] != "processing":
        break
    
    time.sleep(1)

# Получаем результаты
results = requests.get(f"http://localhost:8000/api/results/{task_id}")
print(results.json())
```

**Примеры файлов:**

`phones.txt`:
```
89212810954
+79213456789
89999999999
89123456789
89987654321
```

`phones.csv`:
```
phone
89212810954
79213456789
89999999999
89123456789
89987654321
```

### Пример 4: Batch обработка с сохранением результатов

```python
import requests
import json

# Запускаем проверку
response = requests.post(
    "http://localhost:8000/api/check/batch",
    json={
        "phones": [
            "89212810954",
            "89213456789",
            "89999999999"
        ]
    }
)

task_data = response.json()
task_id = task_data["task_id"]

# Ждём завершения
import time
while True:
    status = requests.get(f"http://localhost:8000/api/status/{task_id}")
    if status.json()["status"] != "processing":
        break
    time.sleep(1)

# Сохраняем результаты
results = requests.get(f"http://localhost:8000/api/results/{task_id}")
with open(f"results_{task_id}.json", "w", encoding="utf-8") as f:
    json.dump(results.json(), f, ensure_ascii=False, indent=2)

print(f"Результаты сохранены в results_{task_id}.json")
```

## 🔧 Форматы номеров

Поддерживаемые форматы:
- `89212810954` (11 цифр, начиная с 8)
- `79212810954` (11 цифр, начиная с 7)
- `+79212810954` (с плюсом)
- `+7 921 281-09-54` (с разделителями)

Все форматы преобразуются в: `+7 921 281-09-54`

## ⚙️ Конфигурация

### Максимум одновременных проверок

```python
# В checker.py
MAX_CONCURRENT_CHECKS = 15  # можно изменить
```

### TTL кеша результатов

```python
# В checker.py
_PHONE_CACHE_TTL = 3600  # 1 час
```

### Максимум номеров в batch запросе

```python
# В server.py
if len(request.phones) > 500:  # максимум 500
```

## 🐛 Отладка

### Запуск с логами

```bash
python server.py 2>&1 | tee server.log
```

### Проверка сервера локально

```bash
curl http://localhost:8000/health
```

### Запрос с повышенным логированием

Сервер выводит все логи в консоль автоматически.

## 📊 Мониторинг

Используйте `/api/status/{task_id}` для отслеживания прогресса:

```bash
# Проверить статус в реальном времени
while true; do
  curl http://localhost:8000/api/status/f47ac10b-58cc-4372-a567-0e02b2c3d479
  sleep 1
done
```

## ⚠️ Ограничения

- Максимум 500 номеров за раз
- Максимум 15 одновременных проверок (по умолчанию)
- Результаты кешируются на 1 час
- Статистика сохраняется в `stats.json`

## 🔐 Безопасность

- Сервер не требует аутентификации (добавить если нужно)
- Номера телефонов логируются в консоль и в памяти сервера
- Для production окружения рекомендуется добавить:
  - API Key аутентификацию
  - Rate limiting
  - CORS политику
  - HTTPS

## 📝 Лицензия

Используется с ботом Yandex Phone Checker CTF
