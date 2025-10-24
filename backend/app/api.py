from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import os
import shutil
import uuid
from datetime import datetime
from typing import Dict, Any
import json

router = APIRouter()

# Хранилище статусов задач (временно в памяти, для production использовать БД)
tasks_storage: Dict[str, Dict[str, Any]] = {}

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Загрузка E57 файла
    """
    # Проверка расширения файла
    if not file.filename.endswith('.e57'):
        raise HTTPException(status_code=400, detail="Поддерживаются только .e57 файлы")
    
    # Генерируем уникальный ID для задачи
    task_id = str(uuid.uuid4())
    
    # Путь для сохранения файла
    upload_path = f"uploads/{task_id}.e57"
    
    # Сохраняем файл
    with open(upload_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Создаём запись о задаче
    tasks_storage[task_id] = {
        "id": task_id,
        "filename": file.filename,
        "status": "uploaded",
        "created_at": datetime.now().isoformat(),
        "file_path": upload_path
    }
    
    return {
        "task_id": task_id,
        "filename": file.filename,
        "status": "uploaded",
        "message": "Файл успешно загружен"
    }

@router.get("/status/{task_id}")
async def get_status(task_id: str):
    """
    Получить статус обработки задачи
    """
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    return tasks_storage[task_id]

@router.post("/process/{task_id}")
async def process_task(task_id: str):
    """
    Запустить обработку файла
    """
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    # Обновляем статус
    tasks_storage[task_id]["status"] = "processing"
    
    # TODO: Здесь будет вызов функции обработки
    # from app.processing import process_point_cloud
    # result = process_point_cloud(task_id)
    
    return {
        "task_id": task_id,
        "status": "processing",
        "message": "Обработка запущена"
    }

@router.get("/model/{task_id}")
async def get_model(task_id: str):
    """
    Получить данные модели (облако точек + IFC объекты)
    """
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    model_path = f"models/{task_id}.json"
    
    if not os.path.exists(model_path):
        raise HTTPException(status_code=404, detail="Модель еще не создана")
    
    with open(model_path, "r") as f:
        model_data = json.load(f)
    
    return model_data

@router.put("/model/{task_id}")
async def update_model(task_id: str, updates: Dict[str, Any]):
    """
    Обновить параметры объектов в модели
    """
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    model_path = f"models/{task_id}.json"
    
    if not os.path.exists(model_path):
        raise HTTPException(status_code=404, detail="Модель не найдена")
    
    # Загружаем текущую модель
    with open(model_path, "r") as f:
        model_data = json.load(f)
    
    # Обновляем параметры (простая логика для MVP)
    # TODO: Добавить валидацию и более сложную логику обновления
    model_data.update(updates)
    
    # Сохраняем обновленную модель
    with open(model_path, "w") as f:
        json.dump(model_data, f, indent=2)
    
    return {
        "task_id": task_id,
        "message": "Модель обновлена",
        "updated_fields": list(updates.keys())
    }

@router.get("/export/{task_id}")
async def export_ifc(task_id: str):
    """
    Экспортировать IFC4 файл
    """
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    ifc_path = f"exports/{task_id}.ifc"
    
    if not os.path.exists(ifc_path):
        raise HTTPException(status_code=404, detail="IFC файл еще не создан")
    
    # Возвращаем файл для скачивания
    return FileResponse(
        path=ifc_path,
        filename=f"{tasks_storage[task_id]['filename']}.ifc",
        media_type="application/x-step"
    )