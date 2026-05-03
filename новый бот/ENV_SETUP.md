# 🔐 Переменные окружения (.env)

## ✅ Что было исправлено

❌ **Было:** Hardcoded BOT_TOKEN в коде  
✅ **Стало:** BOT_TOKEN загружается из .env файла

## 📋 Как использовать

### 1️⃣ **Создать .env файл**

**Windows:**
```bash
cd "новый бот"
copy .env.example .env
```

**macOS/Linux:**
```bash
cd "новый бот"
cp .env.example .env
```

### 2️⃣ **Отредактировать .env**

**Откройте `новый бот/.env`:**

```bash
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
BOT_ADMIN_ID=YOUR_ADMIN_ID_HERE
```

### 3️⃣ **Получить новый BOT_TOKEN**

⚠️ **СТАРЫЙ ТОКЕН СКОМПРОМЕТИРОВАН!** Создайте новый:

1. Откройте Telegram
2. Найдите **@BotFather**
3. Напишите `/start`
4. Выберите вашего бота
5. Напишите `/revoke` (отозвать старый токен)
6. Напишите `/newtoken` (создать новый)
7. **Скопируйте новый токен**
8. Вставьте в `.env`:

```bash
BOT_TOKEN=YOUR_NEW_TOKEN
```

### 4️⃣ **Установить зависимости**

```bash
pip install python-dotenv
```

Это уже в `requirements_server.txt`, поэтому:

```bash
pip install -r requirements_server.txt
```

### 5️⃣ **Запустить бота**

```bash
python bot_new.py
```

или

```bash
python bot.py
```

Оба будут загружать BOT_TOKEN из `.env` файла.

---

## 📝 .env.example

```bash
# Telegram Bot Token
# Получите от @BotFather
BOT_TOKEN=your_bot_token_here

# Опционально: Admin ID (для /stats команды)
BOT_ADMIN_ID=your_admin_id_here
```

---

## 🔐 На Ubuntu/Production

### Вариант 1: Через .env файл

```bash
# На сервере создать .env
nano новый\ бот/.env
```

```bash
BOT_TOKEN=your_new_token
```

### Вариант 2: Через переменные окружения

```bash
# Установить переменную
export BOT_TOKEN="your_new_token"

# Или в systemd сервис
# Добавить в [Service] секцию:
Environment="BOT_TOKEN=your_new_token"
```

### Вариант 3: Через Docker

```dockerfile
# В Dockerfile или docker-compose.yml
ENV BOT_TOKEN=your_new_token
```

Или через `docker run`:

```bash
docker run -e BOT_TOKEN="your_new_token" yandex-checker
```

---

## ⚠️ Безопасность

### .env файл НЕ коммитится в git

```bash
# В .gitignore уже добавлено:
.env
.env.local
.env.*.local
```

### При публикации на GitHub:

✅ **Отправляется:** `.env.example` (пример без токена)  
❌ **НЕ отправляется:** `.env` (с реальным токеном)

---

## 🚀 Установка python-dotenv

```bash
pip install python-dotenv
```

Или добавлено в requirements:

```bash
pip install -r requirements_server.txt
```

---

## ✅ Проверка

```bash
# Проверить что .env загружается
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('BOT_TOKEN'))"
```

Должно вывести ваш токен (или None если .env не существует).

---

## 📚 Документация

- [START_HERE.md](START_HERE.md) - быстрый старт
- [SETUP.md](SETUP.md) - полная установка
- [GIT.md](../GIT.md) - git инструкции

---

## 🎯 Итог

| Параметр | Было | Стало |
|----------|------|-------|
| Токен в коде | ❌ Hardcoded | ✅ .env файл |
| Безопасность | 🔴 Низкая | 🟢 Высокая |
| Коммиты | 🔴 Содержат токен | 🟢 Без токена |
| Развертывание | 🔴 Опасно | 🟢 Безопасно |

**Всё готово! Используйте .env для токенов! 🔐**
