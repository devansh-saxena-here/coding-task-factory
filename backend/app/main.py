from fastapi import FastAPI
from app.core.config import APP_NAME
from app.routers import health, tasks

app = FastAPI(title=APP_NAME)

app.include_router(health.router)
app.include_router(tasks.router)
