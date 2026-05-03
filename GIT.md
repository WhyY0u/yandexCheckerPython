# 📋 Git инструкция

## 🚀 Инициализация репозитория

### Если репозиторий ещё не создан

```bash
cd d:\yandexcheck
git init
```

### Если репозиторий уже создан

Просто начните добавлять файлы:

```bash
cd d:\yandexcheck
git status
```

## 📝 Что нужно закоммитить

### Основные файлы (НУЖНЫ)
```
новый бот/
├── checker.py                    ✅ Основной модуль
├── server.py                     ✅ REST API сервер
├── bot_new.py                    ✅ Новая версия бота
├── requirements_server.txt       ✅ Зависимости
├── .gitignore                    ✅ Игнор файлы
├── SERVER_API.md                 ✅ Документация API
├── SETUP.md                      ✅ Установка
├── README_SERVER.md              ✅ Обзор
├── FILE_UPLOAD.md                ✅ Загрузка файлов
├── CHANGES.md                    ✅ История изменений
├── START_HERE.md                 ✅ Быстрый старт
├── example_client.py             ✅ Примеры
└── examples.sh                   ✅ Примеры curl
```

### Опциональные файлы (МОЖНО)
```
├── bot.py                        ⚠️ Старая версия (для совместимости)
├── main.py                       ⚠️ Старые файлы проекта
├── build.py                      ⚠️ Старые файлы проекта
└── pyproject.toml                ⚠️ Старые файлы проекта
```

### НЕ закоммитить (в .gitignore)
```
├── stats.json                    ❌ Генерируется автоматически
├── result_*.txt                  ❌ Результаты проверок
├── test_phones.*                 ❌ Тестовые файлы
├── __pycache__/                  ❌ Python кеш
├── venv/                         ❌ Virtual environment
└── *.log                         ❌ Логи
```

## 📤 Стандартные команды

### 1. Проверить статус
```bash
git status
```

### 2. Добавить все файлы
```bash
git add .
```

### 3. Добавить конкретные файлы
```bash
git add новый\ бот/checker.py
git add новый\ бот/server.py
git add новый\ бот/bot_new.py
git add новый\ бот/*.md
git add новый\ бот/requirements_server.txt
```

### 4. Сделать коммит
```bash
git commit -m "Переделка CTF бота на REST API сервер"
```

### 5. Посмотреть логи
```bash
git log --oneline
```

## 💬 Рекомендуемое сообщение коммита

```
Переделка Yandex CTF бота на REST API сервер

- Извлечена логика проверки в модуль checker.py
- Добавлен FastAPI REST API сервер (server.py)
- Переработан Telegram бот (bot_new.py)
- Добавлена поддержка загрузки файлов
- Добавлена полная документация
- Добавлены примеры использования

Функциональность полностью сохранена:
✅ Все функции проверки идентичны
✅ Кеширование работает
✅ Параллельная обработка работает
✅ Статистика сохраняется
```

## 🌐 Загрузить на GitHub

### 1. Создать репозиторий на GitHub

https://github.com/new

Укажите:
- Name: `yandex-ctf`
- Description: `Yandex CTF phone checker - Bot + REST API Server`
- Visibility: `Public` или `Private`

### 2. Связать локальный репозиторий

```bash
git remote add origin https://github.com/YOUR_USERNAME/yandex-ctf.git
```

### 3. Загрузить на GitHub

```bash
git branch -M main
git push -u origin main
```

## 📊 Структура для GitHub

### Иерархия папок
```
yandex-ctf/
├── 📁 новый бот/
│   ├── checker.py
│   ├── server.py
│   ├── bot_new.py
│   ├── requirements_server.txt
│   └── *.md
├── .gitignore
├── README.md              ← Главный README
└── GIT.md
```

### Главный README.md (для GitHub)

```markdown
# Yandex CTF Phone Checker

REST API сервер + Telegram бот для проверки доступности номеров в Yandex Passport.

## Функциональность

- ✅ Проверка одного номера (синхронно)
- ✅ Проверка пакетов номеров (асинхронно)
- ✅ Загрузка файлов (TXT/CSV)
- ✅ Распознавание капч (OCR)
- ✅ Кеширование результатов
- ✅ REST API (FastAPI)
- ✅ Telegram Bot

## Быстрый старт

```bash
# Установить зависимости
pip install -r "новый бот/requirements_server.txt"

# Запустить сервер
python "новый бот/server.py"

# Или запустить бота
python "новый бот/bot_new.py"
```

Подробнее в [новый бот/START_HERE.md](новый%20бот/START_HERE.md)

## API

```bash
# Проверить один номер
curl -X POST "http://localhost:8000/api/check/phone" \
  -H "Content-Type: application/json" \
  -d '{"phone": "89212810954"}'

# Загрузить файл
curl -X POST "http://localhost:8000/api/check/file" \
  -F "file=@phones.txt"
```

API документация: [новый бот/SERVER_API.md](новый%20бот/SERVER_API.md)

## Документация

- [START_HERE.md](новый%20бот/START_HERE.md) - быстрый старт
- [SERVER_API.md](новый%20бот/SERVER_API.md) - API документация
- [FILE_UPLOAD.md](новый%20бот/FILE_UPLOAD.md) - загрузка файлов
- [SETUP.md](новый%20бот/SETUP.md) - инструкция установки
- [CHANGES.md](новый%20бот/CHANGES.md) - что изменилось

## Требования

- Python 3.8+
- Tesseract OCR
- pip зависимости: fastapi, uvicorn, requests, easyocr, и т.д.

## Лицензия

MIT / Учебный проект
```

## 🔑 Ключевые файлы для git

| Файл | Назначение |
|------|-----------|
| `checker.py` | Основной модуль - ОБЯЗАТЕЛЕН |
| `server.py` | REST API - ОБЯЗАТЕЛЕН |
| `bot_new.py` | Бот - ОБЯЗАТЕЛЕН |
| `requirements_server.txt` | Зависимости - ОБЯЗАТЕЛЕН |
| `*.md` | Документация - ОЧЕНЬ ВАЖНА |
| `.gitignore` | Игнор файлы - ВАЖЕН |
| `bot.py` | Старая версия - ОПЦИОНАЛЬНО |

## 📋 Чек-лист перед коммитом

- ✅ Удалены тестовые файлы (`test_phones.*`)
- ✅ Удалены логи (`*.log`)
- ✅ Удалена статистика (`stats.json`)
- ✅ Удалены результаты (`result_*.txt`)
- ✅ Удалены `__pycache__` папки
- ✅ Удален `venv/` folder
- ✅ `.gitignore` создан
- ✅ Все `.md` файлы добавлены
- ✅ `requirements_server.txt` актуален

## 🚀 Пошаговая инструкция

### Шаг 1: Инициализировать git (если нужно)
```bash
cd d:\yandexcheck
git init
```

### Шаг 2: Добавить все файлы
```bash
git add .
```

### Шаг 3: Проверить что добавится
```bash
git status
```

### Шаг 4: Сделать коммит
```bash
git commit -m "Переделка CTF бота на REST API сервер"
```

### Шаг 5 (опционально): Загрузить на GitHub
```bash
git remote add origin https://github.com/YOUR_USERNAME/yandex-ctf.git
git branch -M main
git push -u origin main
```

## 🐛 Частые проблемы

**Проблема: "fatal: not a git repository"**
```bash
git init
```

**Проблема: Слишком много файлов"**
```bash
# Проверьте .gitignore
cat .gitignore
```

**Проблема: "Permission denied"**
```bash
# Проверьте права доступа
chmod 644 .gitignore
```

## 📊 Размер репозитория

**Без venv и кешей:**
- checker.py: ~35 KB
- server.py: ~18 KB
- bot_new.py: ~12 KB
- Документация: ~50 KB
- **Итого: ~120 KB**

## ✨ Рекомендация

Закоммитьте всё в папке `новый бот/` и `.gitignore`:

```bash
git add "новый бот/"
git add .gitignore
git commit -m "Переделка CTF бота на REST API сервер"
```

Остальные файлы в корне можно не добавлять (старые файлы проекта).

---

**Готово к git! 🚀**
