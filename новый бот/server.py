from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
import json
import time
import os
import sys
import asyncio
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import warnings

warnings.filterwarnings("ignore", message=".*pin_memory.*")

# Импортируем функции из checker.py
import checker

# Создаём FastAPI приложение
app = FastAPI(
    title="Yandex Phone Checker CTF",
    description="API для проверки доступности номеров в Yandex Passport",
    version="1.0.0"
)

# Модели для запросов/ответов
class PhoneCheckRequest(BaseModel):
    phone: str

class BatchCheckRequest(BaseModel):
    phones: List[str]
    max_concurrent: Optional[int] = 15

class CheckResponse(BaseModel):
    phone: str
    status: str  # "registered", "not_registered", "error"
    message: str
    timestamp: str

class BatchStatusResponse(BaseModel):
    task_id: str
    status: str  # "processing", "completed", "failed"
    total: int
    processed: int
    percent: float
    results: List[Dict]
    elapsed_seconds: float
    eta_seconds: Optional[float] = None
    started_at: str
    completed_at: Optional[str] = None

# Хранилище для асинхронных задач
_async_tasks: Dict[str, Dict] = {}
_tasks_lock = threading.Lock()

# Пулл потоков для фоновой обработки
_executor = ThreadPoolExecutor(max_workers=20)

@app.on_event("startup")
async def startup_event():
    """Инициализация при старте сервера"""
    print("🚀 Инициализация Yandex Phone Checker Server...")

    # Проверяем Tesseract
    if not checker.check_tesseract_installed():
        print("⚠️ Tesseract не установлен, OCR может не работать")

    # Настраиваем путь для pytesseract
    checker.setup_tesseract_path()

    # Загружаем статистику
    checker.load_stats()

    # Инициализируем EasyOCR
    print("🔄 Инициализация EasyOCR...")
    checker.get_easyocr_reader()

    print("✅ Сервер готов к работе!")

@app.on_event("shutdown")
async def shutdown_event():
    """Завершение при остановке сервера"""
    print("🛑 Остановка сервера...")
    _executor.shutdown(wait=False)

@app.get("/")
async def root():
    """Корневой endpoint с информацией о сервере"""
    return {
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

@app.get("/health")
async def health_check():
    """Проверка здоровья сервера"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/check/phone", response_model=CheckResponse)
async def check_single_phone(request: PhoneCheckRequest):
    """
    Проверить один номер телефона

    - **phone**: номер телефона в формате 89XXXXXXXXX или +79XXXXXXXXX

    Возвращает результат: registered, not_registered или error
    """
    phone = request.phone.strip()

    # Форматируем номер
    formatted_phone = checker.format_phone_number(phone)
    if not formatted_phone:
        raise HTTPException(
            status_code=400,
            detail=f"Неверный формат номера: {phone}. Используйте 89XXXXXXXXX или +79XXXXXXXXX"
        )

    try:
        # Запускаем проверку в отдельном потоке
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            checker.check_phone,
            formatted_phone,
            None,
            False
        )

        if result == "registered":
            status = "registered"
            message = "✅ Номер зарегистрирован в Yandex"
        elif result == "not_registered":
            status = "not_registered"
            message = "❌ Номер не зарегистрирован в Yandex"
        else:
            status = "error"
            message = "⚠️ Ошибка при проверке (таймаут или проблемы с капчей)"

        return CheckResponse(
            phone=formatted_phone,
            status=status,
            message=message,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        print(f"❌ Ошибка при проверке {formatted_phone}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при проверке: {str(e)}"
        )

@app.post("/api/check/batch")
async def check_batch_phones(request: BatchCheckRequest, background_tasks: BackgroundTasks):
    """
    Проверить несколько номеров (асинхронно)

    - **phones**: список номеров
    - **max_concurrent**: максимум одновременных проверок (по умолчанию 15)

    Возвращает task_id для отслеживания прогресса
    """
    if not request.phones:
        raise HTTPException(status_code=400, detail="Список номеров пуст")

    if len(request.phones) > 500:
        raise HTTPException(status_code=400, detail="Максимум 500 номеров за раз")

    # Форматируем номера
    valid_phones = []
    for phone in request.phones:
        formatted = checker.format_phone_number(phone.strip())
        if formatted:
            valid_phones.append(formatted)

    if not valid_phones:
        raise HTTPException(status_code=400, detail="Нет валидных номеров в списке")

    # Создаём задачу
    task_id = str(uuid.uuid4())

    with _tasks_lock:
        _async_tasks[task_id] = {
            "status": "processing",
            "total": len(valid_phones),
            "processed": 0,
            "results": [],
            "errors": [],
            "started_at": datetime.now(),
            "completed_at": None,
            "max_concurrent": request.max_concurrent or 15
        }

    # Запускаем обработку в фоне
    background_tasks.add_task(
        _process_batch_task,
        task_id,
        valid_phones,
        request.max_concurrent or 15
    )

    return {
        "task_id": task_id,
        "message": f"Начата проверка {len(valid_phones)} номеров",
        "status": "processing"
    }

def _process_batch_task(task_id: str, phones: List[str], max_concurrent: int):
    """Фоновая обработка пакета номеров"""
    try:
        semaphore = threading.Semaphore(max_concurrent)

        def check_single(phone):
            """Проверка одного номера с семафором"""
            acquired = semaphore.acquire(timeout=300)
            if not acquired:
                with _tasks_lock:
                    _async_tasks[task_id]["errors"].append(
                        {"phone": phone, "error": "Таймаут в очереди"}
                    )
                return phone, None

            try:
                result = checker.check_phone(phone, None, False)
                return phone, result
            except Exception as e:
                print(f"❌ Ошибка при проверке {phone}: {e}")
                with _tasks_lock:
                    _async_tasks[task_id]["errors"].append(
                        {"phone": phone, "error": str(e)}
                    )
                return phone, None
            finally:
                semaphore.release()

        # Запускаем все проверки параллельно
        futures = []
        for phone in phones:
            future = _executor.submit(check_single, phone)
            futures.append(future)

        # Собираем результаты по мере завершения
        for future in futures:
            try:
                phone, result = future.result(timeout=300)

                if result == "registered":
                    status = "registered"
                elif result == "not_registered":
                    status = "not_registered"
                else:
                    status = "error"

                with _tasks_lock:
                    _async_tasks[task_id]["results"].append({
                        "phone": phone,
                        "status": status,
                        "checked_at": datetime.now().isoformat()
                    })
                    _async_tasks[task_id]["processed"] += 1
            except Exception as e:
                print(f"❌ Ошибка при получении результата: {e}")
                with _tasks_lock:
                    _async_tasks[task_id]["processed"] += 1

        # Помечаем задачу как завершённую
        with _tasks_lock:
            _async_tasks[task_id]["status"] = "completed"
            _async_tasks[task_id]["completed_at"] = datetime.now()

        print(f"✅ Задача {task_id} завершена: {_async_tasks[task_id]['processed']}/{_async_tasks[task_id]['total']}")

    except Exception as e:
        print(f"❌ Ошибка в задаче {task_id}: {e}")
        with _tasks_lock:
            if task_id in _async_tasks:
                _async_tasks[task_id]["status"] = "failed"
                _async_tasks[task_id]["completed_at"] = datetime.now()

@app.get("/api/status/{task_id}", response_model=BatchStatusResponse)
async def get_task_status(task_id: str):
    """Получить статус проверки пакета номеров"""
    with _tasks_lock:
        if task_id not in _async_tasks:
            raise HTTPException(status_code=404, detail=f"Задача {task_id} не найдена")

        task = _async_tasks[task_id]
        total = task["total"]
        processed = task["processed"]
        percent = (processed / total * 100) if total > 0 else 0

        started = task["started_at"]
        elapsed = (datetime.now() - started).total_seconds()

        # Оценка оставшегося времени
        eta = None
        if processed > 0 and elapsed > 0 and task["status"] == "processing":
            avg_per_phone = elapsed / processed
            remaining = (total - processed) * avg_per_phone
            eta = remaining

        completed_at = task["completed_at"]

        return BatchStatusResponse(
            task_id=task_id,
            status=task["status"],
            total=total,
            processed=processed,
            percent=percent,
            results=task["results"],
            elapsed_seconds=elapsed,
            eta_seconds=eta,
            started_at=started.isoformat(),
            completed_at=completed_at.isoformat() if completed_at else None
        )

@app.get("/api/results/{task_id}")
async def get_task_results(task_id: str):
    """Получить полные результаты проверки пакета"""
    with _tasks_lock:
        if task_id not in _async_tasks:
            raise HTTPException(status_code=404, detail=f"Задача {task_id} не найдена")

        task = _async_tasks[task_id]

        # Подсчитываем статистику
        registered = sum(1 for r in task["results"] if r["status"] == "registered")
        not_registered = sum(1 for r in task["results"] if r["status"] == "not_registered")
        errors = sum(1 for r in task["results"] if r["status"] == "error")

        return {
            "task_id": task_id,
            "status": task["status"],
            "summary": {
                "total": task["total"],
                "processed": task["processed"],
                "registered": registered,
                "not_registered": not_registered,
                "errors": errors,
                "elapsed_seconds": (datetime.now() - task["started_at"]).total_seconds(),
                "started_at": task["started_at"].isoformat(),
                "completed_at": task["completed_at"].isoformat() if task["completed_at"] else None
            },
            "results": task["results"],
            "errors": task["errors"]
        }

@app.get("/api/stats")
async def get_stats():
    """Получить статистику бота"""
    checker.reset_daily_stats_if_needed()

    stats = checker._stats
    return {
        "total_users": len(stats["users"]),
        "total_requests": stats["total_requests"],
        "daily_requests": stats["daily_requests"],
        "last_reset_date": stats["last_reset_date"],
        "active_tasks": len([t for t in _async_tasks.values() if t["status"] == "processing"])
    }

@app.post("/api/check/file")
async def check_file(file: UploadFile = File(...), max_concurrent: int = 15, background_tasks: BackgroundTasks = None):
    """
    Загрузить файл с номерами телефонов

    Поддерживаемые форматы:
    - TXT: один номер на строку
    - CSV: один номер на строку или в первой колонке

    Пример TXT:
    ```
    89212810954
    +79213456789
    89999999999
    ```

    Пример CSV:
    ```
    phone
    89212810954
    79213456789
    89999999999
    ```
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")

    try:
        content = await file.read()
        text = content.decode('utf-8')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {str(e)}")

    # Парсим номера из файла
    valid_phones = []
    lines = text.strip().split('\n')

    for line in lines:
        line = line.strip()

        # Пропускаем пустые строки и заголовки CSV
        if not line or line.lower() in ['phone', 'номер', 'telephone', 'number']:
            continue

        # Пропускаем CSV разделители
        if line.startswith(';') or line.startswith(','):
            continue

        # Берём первое слово (в случае CSV)
        phone = line.split(',')[0].split(';')[0].strip()

        formatted = checker.format_phone_number(phone)
        if formatted:
            valid_phones.append(formatted)

    if not valid_phones:
        raise HTTPException(
            status_code=400,
            detail=f"В файле нет валидных номеров"
        )

    # Создаём задачу (как в batch)
    task_id = str(uuid.uuid4())

    with _tasks_lock:
        _async_tasks[task_id] = {
            "status": "processing",
            "total": len(valid_phones),
            "processed": 0,
            "results": [],
            "errors": [],
            "started_at": datetime.now(),
            "completed_at": None,
            "max_concurrent": max_concurrent,
            "filename": file.filename
        }

    # Запускаем обработку в фоне
    background_tasks.add_task(
        _process_batch_task,
        task_id,
        valid_phones,
        max_concurrent
    )

    return {
        "task_id": task_id,
        "filename": file.filename,
        "message": f"Загружено {len(valid_phones)} номеров из файла {file.filename}",
        "status": "processing"
    }

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Удалить задачу из памяти"""
    with _tasks_lock:
        if task_id in _async_tasks:
            del _async_tasks[task_id]
            return {"message": f"Задача {task_id} удалена"}
        else:
            raise HTTPException(status_code=404, detail=f"Задача {task_id} не найдена")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
