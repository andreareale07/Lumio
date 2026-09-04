"""Unica implementazione di `TaxJurisdiction` in FETTA 1 (SPEC_TAX_REGIME.md).
Pura e sincrona — vedi `app/tax/base.py` per il contratto completo."""
from datetime import date
from decimal import Decimal

from app.tax.base import (
    AssetTaxRef,
    TaxAssetClass,
    TaxRegimeOption,
    TaxRuleset,
    TaxRulesetNotFound,
    TaxTreatment,
    UsableLoss,
    quantize_money,
)
from app.tax.rulesets.italy import IT_RULESETS, TAX_ASSET_CLASSES

# Segnale FORTE richiesto per classificare un ETF come armonizzato:
# asset_type="etf" da solo non basta (un ETC come l'oro fisico puo' avere
# asset_type="etf" nel catalogo per via della regex `_ETF_HINT_RE` usata in
# classificazione, senza esserlo fiscalmente) — serve anche un ISIN UE
# (IE/LU, le due giurisdizioni UCITS piu' comuni) E "UCITS" nel nome.
_UCITS_ISIN_PREFIXES = ("IE", "LU")


def _is_harmonized_etf(ref: AssetTaxRef) -> bool:
    if ref.asset_type != "etf":
        return False
    if not ref.isin or not ref.isin.upper().startswith(_UCITS_ISIN_PREFIXES):
        return False
    if not ref.name or "UCITS" not in ref.name.upper():
        return False
    return True


_REGIMES: tuple[TaxRegimeOption, ...] = (
    TaxRegimeOption(
        code="amministrato", label_key="taxRegime.amministrato", pocket_scope="per_account", calc_model="realized"
    ),
    TaxRegimeOption(
        code="dichiarativo", label_key="taxRegime.dichiarativo", pocket_scope="aggregate", calc_model="realized"
    ),
)


class ItalyTaxJurisdiction:
    code = "IT"
    label_key = "taxJurisdiction.IT"

    def rulesets(self) -> tuple[TaxRuleset, ...]:
        return IT_RULESETS

    def ruleset_at(self, on: date) -> TaxRuleset:
        for ruleset in IT_RULESETS:
            if on >= ruleset.valid_from and (ruleset.valid_until is None or on < ruleset.valid_until):
                return ruleset
        raise TaxRulesetNotFound(f"nessun ruleset IT vigente al {on.isoformat()}")

    def regimes(self, on: date) -> tuple[TaxRegimeOption, ...]:
        return _REGIMES

    def tax_asset_classes(self, on: date) -> tuple[TaxAssetClass, ...]:
        return TAX_ASSET_CLASSES

    def derive_asset_class(self, ref: AssetTaxRef, on: date) -> str | None:
        if ref.asset_type == "cash":
            return None
        if ref.asset_type == "stock":
            return "azioni"
        if ref.asset_type == "bond":
            return "obbligazioni"
        if ref.asset_type == "crypto":
            return "cripto"
        if ref.asset_type == "etf":
            return "etf_armonizzato" if _is_harmonized_etf(ref) else "unclassified"
        return "unclassified"

    def treatment(self, asset_class: str, event_kind: str, on: date) -> TaxTreatment | None:
        return self.ruleset_at(on).treatment_for(asset_class, event_kind)

    def can_offset(self, loss_category: str, gain_category: str, on: date) -> bool:
        return self.ruleset_at(on).can_offset(loss_category, gain_category)

    def usable_loss(self, nominal: Decimal, formation_date: date, on: date) -> UsableLoss:
        ruleset = self.ruleset_at(on)
        conversion = ruleset.conversion_for(formation_date)
        if conversion is None:
            return UsableLoss(
                nominal=nominal, coefficient=Decimal("1"), usable_amount=quantize_money(nominal), conversion_reference=None
            )
        usable = quantize_money(nominal * conversion.coefficient)
        return UsableLoss(
            nominal=nominal,
            coefficient=conversion.coefficient,
            usable_amount=usable,
            conversion_reference=conversion.legal_reference,
        )
