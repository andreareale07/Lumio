from fastapi import APIRouter

from app.api.v1 import accounts, auth, banks, categories, import_mappings, imports, transactions

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(banks.router)
api_router.include_router(accounts.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
api_router.include_router(imports.router)
api_router.include_router(import_mappings.router)
# Le prossime milestone aggiungono qui altri router di dominio (rules, ai, ...).
