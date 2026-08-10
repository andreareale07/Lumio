from fastapi import APIRouter

from app.api.v1 import accounts, auth, banks, categories, transactions

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(banks.router)
api_router.include_router(accounts.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
# Le prossime milestone aggiungono qui altri router di dominio (imports, ...).
