from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    analytics,
    assets,
    auth,
    banks,
    categories,
    import_mappings,
    imports,
    investment_transactions,
    portfolios,
    positions,
    rules,
    settings_ai,
    settings_market_data,
    transaction_type_mappings,
    transactions,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(banks.router)
api_router.include_router(accounts.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
api_router.include_router(imports.router)
api_router.include_router(import_mappings.router)
api_router.include_router(rules.router)
api_router.include_router(settings_ai.router)
api_router.include_router(settings_market_data.router)
api_router.include_router(transaction_type_mappings.router)
api_router.include_router(analytics.router)
api_router.include_router(assets.router)
api_router.include_router(portfolios.router)
api_router.include_router(investment_transactions.router)
api_router.include_router(positions.router)
