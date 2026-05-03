"""
Telegram бот для проверки доступности номеров Yandex
Использует модуль checker для логики проверки
"""

import telebot
import time
import os
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import threading
import warnings

warnings.filterwarnings("ignore", message=".*pin_memory.*")

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Импортируем модуль с логикой проверки
import checker

# Загружаем переменные окружения из .env файла
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️ python-dotenv не установлен, используем переменные окружения напрямую")

# Получаем BOT_TOKEN из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("\n" + "="*60)
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    print("="*60)
    print("\n1. Создайте файл '.env' в папке 'новый бот':")
    print("   BOT_TOKEN=your_bot_token_here")
    print("\n2. Получите токен от @BotFather в Telegram")
    print("\n3. Установите python-dotenv:")
    print("   pip install python-dotenv")
    print("\nИли установите переменную окружения:")
    print("   export BOT_TOKEN=your_token")
    print("="*60 + "\n")
    sys.exit(1)

# Инициализируем бота
bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

# Состояние для отслеживания проверок
_phone_queue = defaultdict(list)
_check_active = defaultdict(bool)
_check_progress = defaultdict(lambda: {"total": 0, "processed": 0, "results": []})
_progress_lock = threading.Lock()

_executor = ThreadPoolExecutor(max_workers=20)

def process_queue(chat_id):
    """Обработка очереди номеров для чата - все номера параллельно, один итоговый файл"""
    global _check_active, _check_progress

    if _check_active[chat_id]:
        return

    _check_active[chat_id] = True

    phones_to_check = list(_phone_queue[chat_id])
    _phone_queue[chat_id] = []

    # Находим и удаляем дубликаты
    seen = []
    duplicates = []
    for phone in phones_to_check:
        if phone in seen:
            if phone not in duplicates:
                duplicates.append(phone)
        else:
            seen.append(phone)
    phones_to_check = seen

    if duplicates:
        dup_text = "\n".join(f"  • {p}" for p in duplicates)
        bot.send_message(chat_id, f"⚠️ Найдены дубликаты ({len(duplicates)} шт.) — исключены из проверки:\n{dup_text}")

    total = len(phones_to_check)

    # Инициализируем прогресс
    with _progress_lock:
        _check_progress[chat_id] = {
            "total": total,
            "processed": 0,
            "results": [],
            "errors": [],
            "started": time.time()
        }

    # Отправляем уведомление о начале
    if total > 10:
        bot.send_message(chat_id, f"🔄 Начата проверка {total} номеров...\n\n⏳ Ожидаемое время: ~{max(30, total // 2)} сек.\n\nИспользуйте /status для просмотра прогресса")

    results = []

    def check_single_phone(phone):
        """Проверка одного номера с обновлением прогресса"""
        result = checker.check_phone(phone, chat_id=None)

        if result == "registered":
            status = "✅"
            detail = "зарегистрирован"
        elif result == "not_registered":
            status = "❌"
            detail = "не зарегистрирован"
        else:
            status = "⚠️"
            detail = "ошибка проверки"

        with _progress_lock:
            _check_progress[chat_id]["processed"] += 1
            result_entry = f"{status} {phone}"
            _check_progress[chat_id]["results"].append(result_entry)

            if result is None:
                _check_progress[chat_id]["errors"].append(f"{phone} — ошибка проверки (таймаут/капча/сеть)")

        return (phone, result)

    # Запускаем все номера параллельно
    futures = []
    for phone in phones_to_check:
        future = _executor.submit(check_single_phone, phone)
        futures.append(future)

    # Ждём завершения всех проверок
    for future in futures:
        try:
            future.result(timeout=180)
        except Exception as e:
            print(f"❌ Ошибка при проверке: {e}")

    # Собираем результаты
    with _progress_lock:
        results = _check_progress[chat_id]["results"].copy()
        errors_list = _check_progress[chat_id]["errors"].copy()
        elapsed = time.time() - _check_progress[chat_id]["started"]
        del _check_progress[chat_id]

    # Формируем итоговый отчёт
    registered = sum(1 for r in results if r.startswith("✅"))
    not_registered = sum(1 for r in results if r.startswith("❌"))
    errors = sum(1 for r in results if r.startswith("⚠️"))

    # Создаём итоговое сообщение
    summary = (
        f"📊 **Итоги проверки**\n\n"
        f"⏱ Время: {elapsed:.1f} сек.\n"
        f"📱 Всего номеров: {total}\n"
        f"✅ Зарегистрировано: {registered}\n"
        f"❌ Не зарегистрировано: {not_registered}\n"
        f"⚠️ Ошибок: {errors}\n\n"
    )

    # Добавляем детали ошибок если есть
    if errors > 0:
        summary += f"🔴 **Номера с ошибками ({len(errors_list)}):**\n"
        for err in errors_list[:10]:
            summary += f"  • {err}\n"
        if len(errors_list) > 10:
            summary += f"  ... и ещё {len(errors_list) - 10}\n"
        summary += "\n"

    # Если номеров много - сохраняем в файл
    if total >= 20:
        filename = f"result_{chat_id}_{int(time.time())}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(summary.replace("**", ""))
            f.write("\n" + "="*50 + "\n\n")
            for result in results:
                f.write(result + "\n")

        try:
            with open(filename, 'rb') as f:
                bot.send_document(chat_id, f, caption=summary, parse_mode="Markdown")
            os.remove(filename)
        except Exception as e:
            print(f"❌ Ошибка отправки файла: {e}")
            bot.send_message(chat_id, summary + "\n".join(results[:50]) + ("\n... и ещё" if len(results) > 50 else ""))
    else:
        full_report = summary + "\n".join(results)
        bot.send_message(chat_id, full_report, parse_mode="Markdown")

    _check_active[chat_id] = False


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message,
        "👋 Привет! Отправь мне номер телефона для проверки.\n\n"
        "📋 **Команды:**\n"
        "/start - Это сообщение\n"
        "/status - Прогресс текущей проверки\n"
        "/skip - Пропустить капчу\n"
        "/id - Узнать chat_id\n"
        "/stats - Статистика бота (для админов)\n\n"
        "📱 **Формат номера:**\n"
        "89212810954 или +79212810954\n\n"
        "📬 **Можно отправлять:**\n"
        "- По одному в сообщении\n"
        "- До 100 номеров сразу (каждый с новой строки)\n\n"
        "⚡ **Оптимизации:**\n"
        "- 100 номеров за 60-90 сек\n"
        "- Гибридное распознавание капч (Tesseract + EasyOCR)\n"
        "- Кеширование сессий\n"
        "- Результат одним файлом")


@bot.message_handler(commands=['id'])
def get_chat_id(message):
    chat_id = message.chat.id
    bot.reply_to(message, f"🆔 Ваш chat_id: {chat_id}")


def escape_markdown_v2(text):
    """Экранирование специальных символов для MarkdownV2"""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


@bot.message_handler(commands=['add'])
def add_trusted(message):
    chat_id = message.chat.id

    if not checker.is_trusted_user(str(chat_id)):
        bot.reply_to(message, "❌ Доступ запрещён")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Использование: /add <chat_id>\n\nПример: /add 123456789")
        return

    try:
        new_trusted_id = args[1]
        checker.add_trusted_user(new_trusted_id)
        bot.reply_to(message, f"✅ Пользователь {escape_markdown_v2(str(new_trusted_id))} добавлен в список доверенных лиц", parse_mode="MarkdownV2")
    except ValueError:
        bot.reply_to(message, "❌ Неверный формат chat_id")


@bot.message_handler(commands=['stats'])
def show_stats(message):
    chat_id = message.chat.id

    if not checker.is_trusted_user(str(chat_id)):
        bot.reply_to(message, "❌ Доступ запрещён.\n\nИспользуйте команду /id для получения вашего chat_id")
        return

    checker.reset_daily_stats_if_needed()

    users_count = len(checker._stats["users"])
    total_requests = checker._stats["total_requests"]
    daily_requests = checker._stats["daily_requests"]

    stats_text = (
        f"📊 *Статистика бота*\n\n"
        f"👥 Пользователей (написали хотя бы 1 сообщение): {users_count}\n"
        f"📈 Всего запросов: {total_requests}\n"
        f"📅 Запросов за сегодня: {daily_requests}"
    )

    bot.reply_to(message, stats_text, parse_mode="Markdown")


@bot.message_handler(commands=['skip'])
def skip_captcha(message):
    chat_id = message.chat.id
    checker.set_skip_flag(chat_id, True)
    bot.reply_to(message, "⚠️ Команда /skip принята. Пропускаю текущую капчу...")


@bot.message_handler(commands=['status'])
def show_status(message):
    chat_id = message.chat.id

    with _progress_lock:
        if chat_id not in _check_progress:
            bot.reply_to(message, "ℹ️ Нет активных проверок в этом чате")
            return

        progress = _check_progress[chat_id]
        total = progress["total"]
        processed = progress["processed"]
        percent = (processed / total * 100) if total > 0 else 0
        elapsed = time.time() - progress.get("started", time.time())

        # Оценка оставшегося времени
        if processed > 0 and elapsed > 0:
            avg_per_number = elapsed / processed
            remaining = (total - processed) * avg_per_number
            eta = f"~{remaining:.0f} сек."
        else:
            eta = "вычисление..."

        status_text = (
            f"📊 **Прогресс проверки**\n\n"
            f"📱 Всего номеров: {total}\n"
            f"✅ Обработано: {processed}/{total}\n"
            f"📈 Прогресс: {percent:.1f}%\n"
            f"⏱ Прошло времени: {elapsed:.1f} сек.\n"
            f"⏳ Осталось: {eta}\n\n"
            f"🔄 Пожалуйста, дождитесь завершения..."
        )

        bot.reply_to(message, status_text, parse_mode="Markdown")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text.strip()

    # Разбиваем сообщение на строки
    lines = text.split('\n')

    # Извлекаем и форматируем номера
    valid_phones = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        formatted_phone = checker.format_phone_number(line)
        if formatted_phone:
            valid_phones.append(formatted_phone)

    # Если нет валидных номеров
    if not valid_phones:
        bot.reply_to(message, "❌ Неверный формат номера.\n\nОтправь номер в формате:\n89212810954 или +79212810954\n\nМожно отправлять несколько номеров сразу (каждый с новой строки)")
        return

    # Подсчёт запросов для статистики
    if chat_id:
        for _ in valid_phones:
            checker.add_user_request(chat_id)

    # Добавляем номера в очередь
    _phone_queue[chat_id].extend(valid_phones)

    if len(valid_phones) == 1 and not _check_active[chat_id]:
        # Один номер - быстрая проверка
        phone = valid_phones[0]
        bot.reply_to(message, f"🔍 Проверяю номер {phone}...")

        future = _executor.submit(checker.check_phone, phone, chat_id=None)
        try:
            result = future.result(timeout=180)
        except Exception as e:
            print(f"❌ Ошибка при проверке {phone}: {e}")
            result = None

        status = "✅" if result == "registered" else ("❌" if result == "not_registered" else "⚠️")
        bot.send_message(chat_id, f"{phone}: {status}")
    else:
        # Несколько номеров или активная проверка - в очередь
        total_queued = len(_phone_queue[chat_id])
        bot.reply_to(message, f"🔍 Добавлено номеров: {len(valid_phones)}\n📋 В очереди: {total_queued}\n\nНачинаю проверку...")

        # Запускаем обработку очереди в пуле потоков
        _executor.submit(process_queue, chat_id)


if __name__ == "__main__":
    # Проверка Tesseract перед запуском
    if not checker.check_tesseract_installed():
        print("\n❌ Бот не запущен: Tesseract OCR не установлен")
        try:
            input("\nНажмите Enter для выхода...")
        except EOFError:
            pass
        sys.exit(1)

    # Настраиваем путь для pytesseract
    checker.setup_tesseract_path()

    # Загружаем статистику и доверенных пользователей
    checker.load_stats()

    # Предварительная инициализация EasyOCR
    print("\n🔄 Предварительная инициализация EasyOCR...")
    checker.get_easyocr_reader()

    print("\n🤖 Бот запущен (многопоточный режим, макс. одновременных проверок: {})...".format(checker.MAX_CONCURRENT_CHECKS))
    try:
        bot.infinity_polling(skip_pending=True, timeout=60)
    except KeyboardInterrupt:
        print("\n🛑 Остановка бота...")
    finally:
        print("🔄 Завершение пула потоков...")
        _executor.shutdown(wait=False)
