"""Registro dei connettori Open Banking (stesso schema di `app/parsers`)."""
from app.openbanking.base import BankConnector
from app.openbanking.enable_banking import EnableBankingConnector

PROVIDER_ENABLE_BANKING = "enable_banking"


def get_connector(provider: str, *, application_id: str, private_key_pem: str) -> BankConnector:
    if provider == PROVIDER_ENABLE_BANKING:
        return EnableBankingConnector(application_id=application_id, private_key_pem=private_key_pem)
    raise ValueError(f"Provider Open Banking sconosciuto: {provider}")
