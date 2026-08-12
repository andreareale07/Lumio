"""Security headers (SPEC §52) applicati a ogni risposta.

CSP omesso per /docs, /redoc, /openapi.json: Swagger/Redoc caricano JS/CSS
da CDN esterna e una CSP stretta li romperebbe; il resto dell'API (solo
JSON, mai markup servito) resta a "default-src 'none'" senza eccezioni.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, https_only: bool = False) -> None:
        super().__init__(app)
        self._https_only = https_only

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if request.url.path not in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if self._https_only:
            # Solo in produzione (SPEC §52: HTTPS in deployment) — in sviluppo
            # locale su http:// l'header verrebbe ignorato dal browser ma
            # e' comunque piu' chiaro non inviarlo affatto.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
