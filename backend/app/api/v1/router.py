from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    activity,
    analytics,
    assets,
    auth,
    banks,
    categories,
    classification,
    currencies,
    import_mappings,
    imports,
    integrations_google,
    investment_transactions,
    jobs,
    portfolios,
    positions,
    rules,
    settings_ai,
    settings_market_data,
    system_settings,
    tax,
    transaction_type_mappings,
    transactions,
    workspace,
)
from app.core.config import get_settings

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
api_router.include_router(system_settings.router)
api_router.include_router(jobs.router)
api_router.include_router(classification.router)
api_router.include_router(activity.router)
api_router.include_router(currencies.router)
api_router.include_router(workspace.router)
api_router.include_router(tax.router)

# Milestone 10: isolamento reale, non solo un check a runtime (ROADMAP DoD
# "con GOOGLE_ENABLED=false nessuna funzionalita' core e' impattata") — con
# il flag disattivato questi endpoint non esistono affatto (404 generico),
# non solo rifiutano la richiesta.
if get_settings().google_enabled:
    api_router.include_router(integrations_google.router)
