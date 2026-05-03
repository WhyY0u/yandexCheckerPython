# 🎯 Yandex Phone Checker CTF - Server Version

Это REST API сервер для проверки доступности номеров телефонов в Yandex Passport с поддержкой асинхронной обработки пакетов.

## ✨ Что было переделано

Исходный код бота был переструктурирован:

### Было:
- `bot.py` - один большой файл с логикой и Telegram ботом
- Трудно переиспользовать логику
- Трудно интегрировать с другими системами

### Стало:
- `checker.py` - чистый модуль с логикой проверки ✅
- `bot_new.py` - облегченный Telegram бот (использует `checker.py`)
- `server.py` - REST API сервер (использует `checker.py`)
- Легко переиспользовать логику в других приложениях

### Всё осталось работать так же:
✅ Все функции проверки номеров идентичны  
✅ Кеширование работает на том же уровне  
✅ Распознавание капч (Tesseract + EasyOCR) не изменилось  
✅ Параллельная обработка работает одинаково  
✅ Статистика и прогресс отслеживаются корректно  

## 📁 Структура файлов

```
новый бот/
├── checker.py                 ← Модуль с логикой (ядро)
├── bot.py                     ← Старая версия (для совместимости)
├── bot_new.py                 ← Новая версия бота (использует checker)
├── server.py                  ← FastAPI сервер (использует checker)
├── example_client.py          ← Примеры использования API
├── examples.sh                ← Curl примеры
├── requirements_server.txt    ← Зависимости
├── install.bat                ← Установка на Windows
├── SETUP.md                   ← Инструкция установки
├── SERVER_API.md              ← Полная документация API
├── README_SERVER.md           ← Этот файл
└── stats.json                 ← Статистика (создаётся автоматически)
```

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Windows
install.bat

# macOS/Linux
pip install -r requirements_server.txt
```

### 2. Запуск сервера

```bash
python server.py
```

Сервер запустится на `http://localhost:8000`

### 3. Тестирование

```bash
# Проверить здоровье
curl http://localhost:8000/health

# Или использовать Python скрипт
python example_client.py
```

## 📚 API Endpoints

### ✅ Синхронная проверка одного номера
```
POST /api/check/phone
{ "phone": "89212810954" }
→ { "status": "registered" }
```

### ⚙️ Асинхронная проверка пакета
```
POST /api/check/batch
{ "phones": ["89212810954", "89213456789"], "max_concurrent": 15 }
→ { "task_id": "..." }
```

### 📊 Статус задачи
```
GET /api/status/{task_id}
→ { "status": "processing", "processed": 2, "total": 10, ... }
```

### 📋 Результаты
```
GET /api/results/{task_id}
→ { "results": [...], "summary": {...} }
```

### 📈 Статистика
```
GET /api/stats
→ { "total_users": 42, "total_requests": 1234, ... }
```

Подробнее в [SERVER_API.md](SERVER_API.md)

## 🔄 Как это работает

### Архитектура

```
Telegram Bot (bot_new.py)  ─┐
                             ├─→ checker.py (Логика проверки)
FastAPI Server (server.py) ─┘    ├─ Yandex API
                                 ├─ OCR (Tesseract + EasyOCR)
                                 ├─ Кеширование
                                 └─ Параллельная обработка
```

### Поток данных (API)

```
1. POST /api/check/batch
   ↓
2. Создаём task_id
   ↓
3. Запускаем обработку в фоне (_process_batch_task)
   ↓
4. Клиент опрашивает GET /api/status/{task_id}
   ↓
5. Результаты готовы → GET /api/results/{task_id}
```

## 💡 Примеры использования

### Пример 1: Curl (одна команда)

```bash
curl -X POST "http://localhost:8000/api/check/phone" \
  -H "Content-Type: application/json" \
  -d '{"phone": "89212810954"}'
```

### Пример 2: Python (асинхронная обработка)

```python
import requests
import time

# Запуск
r = requests.post(
    "http://localhost:8000/api/check/batch",
    json={"phones": ["89212810954", "89213456789"]}
)
task_id = r.json()["task_id"]

# Ждём завершения
while True:
    status = requests.get(f"http://localhost:8000/api/status/{task_id}")
    if status.json()["status"] != "processing":
        break
    time.sleep(1)

# Результаты
results = requests.get(f"http://localhost:8000/api/results/{task_id}")
print(results.json())
```

### Пример 3: Batch обработка с сохранением

```python
import requests

# Проверить 100 номеров в 2 батчах
phones = [f"8921281095{i}" for i in range(100)]

tasks = []
for i in range(0, len(phones), 50):
    r = requests.post(
        "http://localhost:8000/api/check/batch",
        json={"phones": phones[i:i+50]}
    )
    tasks.append(r.json()["task_id"])

# Ждём завершения всех
# ... и сохраняем результаты
```

Больше примеров в [example_client.py](example_client.py)

## ⚙️ Конфигурация

### Максимум одновременных проверок

```python
# В checker.py (строка 30)
MAX_CONCURRENT_CHECKS = 15
```

### TTL кеша результатов

```python
# В checker.py (строка 51)
_PHONE_CACHE_TTL = 3600  # 1 час
```

### Максимум номеров в batch

```python
# В server.py (строка ~150)
if len(request.phones) > 500:  # Измените на нужное
```

## 🔒 Безопасность

### Текущий статус
- ⚠️ Нет аутентификации
- ⚠️ Нет rate limiting
- ⚠️ Нет HTTPS

### Для production

Добавьте в `server.py`:

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_api_key(credentials: HTTPBearer):
    if credentials.credentials != "YOUR_SECRET_KEY":
        raise HTTPException(status_code=401)
    return credentials.credentials

@app.post("/api/check/phone", dependencies=[Depends(verify_api_key)])
async def check_single_phone(...):
    ...
```

## 📊 Мониторинг и отладка

### Проверить сервер

```bash
# Здоровье
curl http://localhost:8000/health

# Информация
curl http://localhost:8000/

# Статистика
curl http://localhost:8000/api/stats
```

### Логирование

```bash
# С сохранением логов
python server.py 2>&1 | tee server.log

# С DEBUG логированием
DEBUG=true python server.py
```

### Отслеживание задачи

```bash
# Мониторить в реальном времени
watch -n 1 'curl -s http://localhost:8000/api/status/{task_id} | jq'
```

## 🧪 Тестирование

### Быстрый тест

```bash
python example_client.py
# Выберите пример 1 или 3
```

### Полный тест

```bash
# Терминал 1: Запустить сервер
python server.py

# Терминал 2: Запустить примеры
bash examples.sh
```

## ⚠️ Требования

1. **Python 3.8+**
2. **Tesseract OCR** - отдельно устанавливается
   - [Windows](https://github.com/UB-Mannheim/tesseract/wiki)
   - macOS: `brew install tesseract`
   - Linux: `apt-get install tesseract-ocr`

## 🐛 Частые проблемы

**Q: ModuleNotFoundError: easyocr**
```bash
pip install -r requirements_server.txt
```

**Q: Tesseract не найден**
```bash
python -c "import checker; checker.check_tesseract_installed()"
```

**Q: Порт 8000 занят**
```bash
# Используйте другой порт в server.py
# В конце файла: uvicorn.run(app, port=8001)
```

**Q: Капча не распознается**
- Проверьте Tesseract
- Попробуйте обновить EasyOCR: `pip install --upgrade easyocr`

## 📈 Производительность

### Бенчмарк

```
Конфигурация: 15 одновременных проверок
- 100 номеров: ~60-90 сек
- 1000 номеров: ~10-15 мин

Зависит от:
- Скорости интернета
- Требует ли капча
- Нагрузки на Yandex API
```

### Оптимизация

1. **Увеличить одновременные проверки:**
   ```python
   MAX_CONCURRENT_CHECKS = 30
   ```

2. **Кешировать результаты:**
   ```python
   _PHONE_CACHE_TTL = 7200  # 2 часа
   ```

3. **Использовать GPU для OCR:**
   ```python
   # В checker.py: gpu=True (по умолчанию)
   _easyocr_reader = easyocr.Reader(['en'], gpu=True)
   ```

## 🔗 Интеграция с другими системами

### Прямое использование checker.py

```python
import checker

# Инициализация
checker.check_tesseract_installed()
checker.setup_tesseract_path()
checker.load_stats()
checker.get_easyocr_reader()

# Использование
result = checker.check_phone("+7 921 281-09-54")
print(result)  # "registered" или "not_registered"
```

### Webhook интеграция

Добавьте в `server.py`:

```python
import httpx

async def send_webhook(task_id: str):
    results = _async_tasks[task_id]
    await httpx.post(
        "https://your-webhook.com/callback",
        json={"task_id": task_id, "results": results}
    )
```

## 📝 Лицензия

Используется с учебными целями для Yandex CTF.

## 🚀 Следующие шаги

- [ ] Добавить API Key аутентификацию
- [ ] Добавить rate limiting
- [ ] Добавить HTTPS поддержку
- [ ] Добавить WebSocket для real-time статуса
- [ ] Добавить базу данных для истории
- [ ] Добавить dashboard для мониторинга

## 💬 Помощь

**Сервер не запускается?**
```bash
python server.py
# Проверьте порт 8000 и зависимости
```

**Капча не решается?**
```bash
python -c "import checker; checker.check_tesseract_installed()"
```

**Нужна консультация?**
- Читайте [SERVER_API.md](SERVER_API.md)
- Смотрите примеры в [example_client.py](example_client.py)
- Запустите bash примеры: `bash examples.sh`

---

**Удачи! 🎉**

Server v1.0.0 | API v1.0.0
