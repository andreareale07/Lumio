from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1 import health
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.core.security_headers import SecurityHeadersMiddleware

setup_logging()

settings = get_settings()

app = FastAPI(title=settings.app_name, description=settings.app_tagline)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware, https_only=settings.app_env == "production")

app.include_router(health.router)
app.include_router(api_router, prefix="/api/v1")
