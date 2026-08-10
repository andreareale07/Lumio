from fastapi import FastAPI

from app.api.v1 import health
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging

setup_logging()

settings = get_settings()

app = FastAPI(title=settings.app_name, description=settings.app_tagline)

app.include_router(health.router)
app.include_router(api_router, prefix="/api/v1")
