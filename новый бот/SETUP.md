# Yandex Phone Checker CTF - Установка и запуск

Есть два способа использовать этот инструмент:
1. **Telegram Bot** - для проверки через Telegram
2. **REST API Server** - для автоматизации и интеграции

## 📦 Установка зависимостей

### Все версии (Bot + Server)

```bash
pip install -r requirements_server.txt
```

Если нужен только бот, также установите:
```bash
pip install pytelegrambotapi
```

## 🤖 Telegram Bot

### Запуск

```bash
python bot_new.py
```

### Функциональность

- Проверка одного номера: просто отправьте номер
- Проверка нескольких: отправьте несколько номеров (каждый с новой строки)
- Команды:
  - `/start` - информация о боте
  - `/status` - прогресс текущей проверки
  - `/skip` - пропустить капчу
  - `/id` - получить chat_id
  - `/stats` - статистика (только для админов)

### Форматы номеров

- `89212810954`
- `79212810954`
- `+79212810954`
- `+7 921 281-09-54`

## 🚀 REST API Server

### Запуск

```bash
python server.py
```

Сервер запустится на `http://localhost:8000`

### Быстрые примеры

#### Проверить один номер (синхронно)

```bash
curl -X POST "http://localhost:8000/api/check/phone" \
  -H "Content-Type: application/json" \
  -d '{"phone": "89212810954"}'
```

#### Проверить несколько номеров (асинхронно)

```bash
curl -X POST "http://localhost:8000/api/check/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "phones": ["89212810954", "89213456789"],
    "max_concurrent": 15
  }'
```

#### Проверить статус задачи

```bash
curl "http://localhost:8000/api/status/{task_id}"
```

#### Получить результаты

```bash
curl "http://localhost:8000/api/results/{task_id}"
```

### Документация API

Смотрите [SERVER_API.md](SERVER_API.md) для полной документации.

## 🔧 Структура проекта

```
новый бот/
├── checker.py              # Основной модуль с логикой проверки
├── bot_new.py              # Telegram бот (использует checker.py)
├── server.py               # REST API сервер (использует checker.py)
├── bot.py                  # Старая версия бота (не обновляется)
├── requirements_server.txt # Зависимости
├── SERVER_API.md           # API документация
├── SETUP.md                # Этот файл
└── stats.json              # Статистика (создаётся автоматически)
```

## 🔑 Переменные окружения

### BOT_TOKEN

Telegram Bot Token (встроен в код, но можно переопределить):

```bash
export BOT_TOKEN="your_token_here"
```

### BOT_ADMIN_ID

Admin chat ID для статистики:

```bash
export BOT_ADMIN_ID="123456789"
```

## 🧪 Тестирование

### Проверить сервер

```bash
curl http://localhost:8000/health
```

### Python скрипт для тестирования batch операции

```python
import requests
import time

# Запустить проверку
r = requests.post(
    "http://localhost:8000/api/check/batch",
    json={"phones": ["89212810954", "89213456789"]}
)

task_id = r.json()["task_id"]
print(f"Task ID: {task_id}")

# Проверять статус каждую секунду
while True:
    status = requests.get(f"http://localhost:8000/api/status/{task_id}")
    data = status.json()
    
    print(f"Progress: {data['processed']}/{data['total']} ({data['percent']:.1f}%)")
    
    if data["status"] != "processing":
        break
    
    time.sleep(1)

# Получить результаты
results = requests.get(f"http://localhost:8000/api/results/{task_id}")
print(results.json())
```

## 🐛 Отладка

### Требования

1. **Tesseract OCR** - необходимо установить отдельно
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki
   - macOS: `brew install tesseract`
   - Linux: `apt-get install tesseract-ocr`

2. **Python 3.8+**

3. **CUDA** (опционально, для GPU в EasyOCR)

### Проверить установку

```bash
python -c "import checker; checker.check_tesseract_installed()"
```

### Логирование

Оба приложения выводят логи в консоль:

```bash
# Бот с логами
python bot_new.py 2>&1 | tee bot.log

# Сервер с логами
python server.py 2>&1 | tee server.log
```

## 📊 Мониторинг

### Статистика бота

```bash
curl http://localhost:8000/api/stats
```

### Активные задачи

Запросите `/api/stats` чтобы увидеть количество активных задач.

## ⚙️ Конфигурация

### Максимум одновременных проверок

В `checker.py`:
```python
MAX_CONCURRENT_CHECKS = 15  # Измените на нужное значение
```

### TTL кеша результатов

В `checker.py`:
```python
_PHONE_CACHE_TTL = 3600  # 1 час
```

### Сессия кеш (для бота/сервера)

В `checker.py`:
```python
_session_cache = {
    "max_uses": 10,  # Переиспользовать сессию на 10 номеров
    "ttl": 300       # Кеш на 5 минут
}
```

## 🚀 Производство

Для production окружения:

### Сервер

```bash
# Используйте Gunicorn + Uvicorn
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker server:app --bind 0.0.0.0:8000
```

### Добавить безопасность

Отредактируйте `server.py` чтобы добавить:
- API Key аутентификацию
- Rate limiting
- CORS политику
- HTTPS

## 🤝 Использование обеих программ

Можно запустить бот и сервер одновременно - они будут использовать один и тот же файл `stats.json` и кеши:

```bash
# Терминал 1
python bot_new.py

# Терминал 2
python server.py
```

Оба будут работать независимо и обновлять общую статистику.

## 📝 Миграция со старой версии

Старый файл `bot.py` оставлен для совместимости. Если хотите использовать новую версию:

```bash
# Переименуйте старый
mv bot.py bot_old.py

# Используйте новый
python bot_new.py
```

Все функции остаются теми же, но код оптимизирован.

## ❓ FAQ

**В:** Какой способ выбрать - бот или сервер?

**О:** 
- **Бот**: если нужна удобная Telegram интерфейс
- **Сервер**: если нужна автоматизация или интеграция с другими системами
- **Оба**: запустите параллельно, они не конфликтуют

---

**В:** Почему капча не распознается?

**О:** Проверьте установку Tesseract OCR. Запустите:
```bash
python -c "import checker; checker.check_tesseract_installed()"
```

---

**В:** Как добавить API Key для безопасности?

**О:** Отредактируйте `server.py` и добавьте middleware для проверки ключа. Пример добавлю если нужно.

---

**В:** Можно ли проверить сразу 1000 номеров?

**О:** Максимум 500 в одном batch запросе. Можно отправить несколько запросов:

```python
phones = [...]  # 1000 номеров

for i in range(0, len(phones), 500):
    batch = phones[i:i+500]
    # Отправить batch запрос
```

## 📞 Контакты

- Telegram бот: https://t.me/YandexPhoneChecker
- API документация: [SERVER_API.md](SERVER_API.md)
