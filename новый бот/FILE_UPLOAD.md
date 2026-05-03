# 📁 Загрузка файлов с номерами

Новый endpoint `/api/check/file` позволяет загружать файлы с номерами вместо отправки JSON.

## ✨ Что поддерживается

### Формат TXT (один номер на строку)

**phones.txt:**
```
89212810954
+79213456789
89999999999
89123456789
89987654321
```

### Формат CSV (с заголовком)

**phones.csv:**
```
phone
89212810954
79213456789
89999999999
89123456789
89987654321
```

Или с другим именем колонки:
```
номер
89212810954
79213456789
```

## 🚀 Использование

### Через curl

```bash
# TXT файл
curl -X POST "http://localhost:8000/api/check/file" \
  -F "file=@phones.txt" \
  -F "max_concurrent=15"

# CSV файл
curl -X POST "http://localhost:8000/api/check/file" \
  -F "file=@phones.csv" \
  -F "max_concurrent=20"
```

### Через Python

```python
import requests

with open("phones.txt", "rb") as f:
    files = {"file": f}
    data = {"max_concurrent": 15}
    
    response = requests.post(
        "http://localhost:8000/api/check/file",
        files=files,
        data=data
    )

task_id = response.json()["task_id"]
print(f"Task ID: {task_id}")
```

### Через Python (более полный пример)

```python
import requests
import time

# Загружаем файл
with open("phones.txt", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/check/file",
        files={"file": f},
        data={"max_concurrent": 15}
    )

task_id = response.json()["task_id"]
print(f"Задача создана: {task_id}")

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
summary = results.json()["summary"]

print(f"\n✅ Зарегистрировано: {summary['registered']}")
print(f"❌ Не зарегистрировано: {summary['not_registered']}")
print(f"⚠️ Ошибок: {summary['errors']}")
```

## 📊 Response

```json
{
  "task_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "filename": "phones.txt",
  "message": "Загружено 1000 номеров из файла phones.txt",
  "status": "processing"
}
```

## 🧪 Тестирование

Используйте встроенный скрипт:

```bash
python test_file_upload.py
```

Скрипт:
1. ✅ Создаст тестовые TXT и CSV файлы
2. ✅ Загрузит их в сервер
3. ✅ Будет отслеживать прогресс
4. ✅ Выведет результаты

## ⚙️ Параметры

### file (обязателен)
Файл для загрузки (TXT или CSV)

### max_concurrent (опционально)
Максимум одновременных проверок (по умолчанию 15)

```bash
curl -X POST "http://localhost:8000/api/check/file" \
  -F "file=@phones.txt" \
  -F "max_concurrent=30"
```

## 🎯 Форматы номеров в файле

Все эти форматы поддерживаются:
- `89212810954` ✅
- `79212810954` ✅
- `+79212810954` ✅
- `+7 921 281-09-54` ✅

## 📈 Производительность

- TXT файл с 1000 номеров: ~10-15 мин
- CSV файл с 500 номеров: ~5-8 мин
- Максимум 500 номеров в одном batch

**Совет:** Если у вас 10000 номеров, разделите на 20 файлов по 500.

## 🔧 Как создать файл со своими номерами

### На Windows

**1. Notepad:**
```
Создать файл → Вставить номера (каждый на новой строке) → Сохранить как phones.txt
```

**2. PowerShell:**
```powershell
$phones = @"
89212810954
+79213456789
89999999999
"@

$phones | Out-File -Path phones.txt -Encoding UTF8
```

### На macOS/Linux

**1. Создать файл:**
```bash
cat > phones.txt << EOF
89212810954
+79213456789
89999999999
EOF
```

**2. Или использовать Python:**
```python
phones = ["89212810954", "79213456789", "89999999999"]
with open("phones.txt", "w") as f:
    f.write("\n".join(phones))
```

## ⚠️ Ограничения

- Максимум 500 номеров в одном запросе
- Файл должен быть в кодировке UTF-8
- Максимум размер файла: зависит от вашего сервера

## 🐛 Частые ошибки

**Ошибка: "Файл не найден"**
```bash
# Убедитесь что файл в текущей папке
ls phones.txt
```

**Ошибка: "В файле нет валидных номеров"**
```
Проверьте формат файла:
- Один номер на строку
- Номера в формате 89XXXXXXXXX или +79XXXXXXXXX
```

**Ошибка: "Нет доступа к файлу"**
```bash
# Проверьте права доступа
chmod 644 phones.txt
```

## 📞 Примеры файлов

### TXT файл (просто номера)

**input.txt:**
```
89212810954
+79213456789
89999999999
89123456789
```

### CSV файл (с заголовком)

**contacts.csv:**
```csv
phone,name
89212810954,Иван
79213456789,Петр
89999999999,Сергей
```

### CSV файл (Excel)

Экспортируйте из Excel как CSV, первая колонка должна содержать номера.

## 🎉 Готово!

Просто загрузите файл и получайте результаты асинхронно!

```bash
# Загрузить
curl -X POST "http://localhost:8000/api/check/file" \
  -F "file=@phones.txt"

# Получить результаты
curl "http://localhost:8000/api/results/{task_id}"
```
