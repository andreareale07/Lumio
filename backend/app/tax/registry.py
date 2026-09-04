"""Registro delle giurisdizioni fiscali — stessa forma di
`app/parsers/__init__.py`. Aggiungere una giurisdizione significa:
implementare `TaxJurisdiction`, aggiungere l'istanza a `JURISDICTIONS`,
tradurre `label_key` nei namespace i18n — nessuna modifica ai servizi
fiscali (`tax_context.py`, `tax_calc.py`, ...)."""
from app.tax.base import TaxJurisdiction
from app.tax.jurisdictions.italy import ItalyTaxJurisdiction

JURISDICTIONS: tuple[TaxJurisdiction, ...] = (ItalyTaxJurisdiction(),)


def get_jurisdiction(code: str) -> TaxJurisdiction:
    for j in JURISDICTIONS:
        if j.code == code:
            return j
    raise ValueError(f"nessuna giurisdizione fiscale registrata per code={code!r}")


__all__ = ["JURISDICTIONS", "get_jurisdiction", "TaxJurisdiction"]
