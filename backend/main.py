from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from app.api import router

# Создаём приложение FastAPI
app = FastAPI(
    title="E57 to IFC Converter API",
    description="API для конвертации облаков точек E57 в BIM модели IFC4",
    version="1.0.0"
)

# Настройка CORS (чтобы frontend мог обращаться к backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В production заменить на конкретный домен
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутер с endpoints
app.include_router(router, prefix="/api")

# Главная страница API
@app.get("/")
def read_root():
    return {
        "message": "E57 to IFC Converter API",
        "version": "1.0.0",
        "status": "running"
    }

# Запуск сервера
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)