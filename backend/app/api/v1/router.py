from fastapi import APIRouter

from app.api.v1 import auth

api_router = APIRouter()
api_router.include_router(auth.router)
# Le prossime milestone aggiungono qui altri router di dominio (accounts, transactions, ...).
