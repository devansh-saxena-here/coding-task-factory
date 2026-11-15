from fastapi import FastAPI
from app.core.config import APP_NAME
from app.routers import health

app = FastAPI(title=APP_NAME)

app.include_router(health.router)
