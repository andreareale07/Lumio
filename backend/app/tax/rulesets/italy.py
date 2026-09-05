"""`IT_RULESETS` — unica fonte di verita' del regolamento fiscale italiano sui
redditi di capitale/diversi da strumenti finanziari (SPEC_TAX_REGIME.md,
FETTA 1). Dato puro, copertura temporale contigua e senza sovrapposizioni fra
le tre versioni (garantito da `test_tax_rulesets.py`, non da un vincolo a
runtime: sono letterali, non un dato utente).

Event kind modellati in FETTA 1: `sale` (evento realizzativo — plusvalenza o
minusvalenza da cessione) e `income` (cedola/dividendo, sempre reddito di
capitale, mai una perdita). Il motore a lotti che genera eventi `sale` dai
movimenti reali e' FETTA 2 — qui esiste solo il trattamento fiscale.

⚠️ `0.26 * 0.4808 = 0.125008`, non 12,5% esatti — sono i coefficienti LEGALI
(DL 66/2014), non la frazione 12,5/26. Non "correggere" sostituendo con
`Decimal("12.5") / Decimal("26")`: il test di invarianza usa tolleranza
1e-5 apposta.
"""
from datetime import date
from decimal import Decimal

from app.tax.base import (
    CarryForwardRule,
    LossConversion,
    OffsetRule,
    TaxAssetClass,
    TaxRuleset,
    TaxTreatment,
)

# Classi fiscali dichiarate dalla giurisdizione italiana — stabili nel tempo,
# indipendenti dalla versione di ruleset vigente (decisione di copertura:
# l'architettura elenca tutte le classi fin da subito, solo alcune sono
# "codified" con un trattamento verificato su fonti solide).
TAX_ASSET_CLASSES: tuple[TaxAssetClass, ...] = (
    TaxAssetClass(code="azioni", label_key="taxAssetClassification.azioni", codified=True),
    TaxAssetClass(code="etf_armonizzato", label_key="taxAssetClassification.etf_armonizzato", codified=True),
    TaxAssetClass(code="obbligazioni", label_key="taxAssetClassification.obbligazioni", codified=True),
    TaxAssetClass(
        code="titoli_stato_whitelist", label_key="taxAssetClassification.titoli_stato_whitelist", codified=True
    ),
    TaxAssetClass(code="cripto", label_key="taxAssetClassification.cripto", codified=False),
    TaxAssetClass(code="derivati", label_key="taxAssetClassification.derivati", codified=False),
    TaxAssetClass(
        code="etf_non_armonizzato", label_key="taxAssetClassification.etf_non_armonizzato", codified=False
    ),
    TaxAssetClass(code="certificati", label_key="taxAssetClassification.certificati", codified=False),
    TaxAssetClass(code="unclassified", label_key="taxAssetClassification.unclassified", codified=False),
)

_CARRY_FORWARD = CarryForwardRule(
    years=4,
    assumption=True,
    assumption_note=(
        "FISCAL ASSUMPTION REQUIRING VALIDATION: consumo FIFO per anno di "
        "formazione — prassi bancaria diffusa, non norma esplicita dell'art. "
        "68 TUIR, che fissa solo il limite di 4 anni."
    ),
)

# Compensazione: default deny (assenza di regola = non compensabile).
# `redditi_diversi` compensa solo se stesso — la plusvalenza ETF armonizzato
# (redditi_capitale) resta fuori dalla matrice per costruzione, senza un
# `if` esplicito nel motore.
_OFFSET_RULES = (OffsetRule(loss_category="redditi_diversi", gain_category="redditi_diversi"),)


def _treatments(rate: Decimal, legal_reference: str, sale_coefficient_titoli_stato: Decimal = Decimal("1")) -> tuple[TaxTreatment, ...]:
    return (
        TaxTreatment(
            asset_class="azioni",
            event_kind="sale",
            gain_category="redditi_diversi",
            loss_category="redditi_diversi",
            status="codified",
            rate=rate,
            taxable_coefficient=Decimal("1"),
            legal_reference=legal_reference,
        ),
        TaxTreatment(
            asset_class="etf_armonizzato",
            event_kind="sale",
            gain_category="redditi_capitale",
            loss_category="redditi_diversi",
            status="codified",
            rate=rate,
            taxable_coefficient=Decimal("1"),
            legal_reference=legal_reference,
        ),
        TaxTreatment(
            asset_class="etf_armonizzato",
            event_kind="income",
            gain_category="redditi_capitale",
            loss_category="redditi_diversi",
            status="codified",
            rate=rate,
            taxable_coefficient=Decimal("1"),
            legal_reference=legal_reference,
        ),
        TaxTreatment(
            asset_class="obbligazioni",
            event_kind="sale",
            gain_category="redditi_diversi",
            loss_category="redditi_diversi",
            status="codified",
            rate=rate,
            taxable_coefficient=Decimal("1"),
            legal_reference=legal_reference,
        ),
        TaxTreatment(
            asset_class="obbligazioni",
            event_kind="income",
            gain_category="redditi_capitale",
            loss_category="redditi_diversi",
            status="codified",
            rate=rate,
            taxable_coefficient=Decimal("1"),
            legal_reference=legal_reference,
        ),
        TaxTreatment(
            asset_class="titoli_stato_whitelist",
            event_kind="sale",
            gain_category="redditi_diversi",
            loss_category="redditi_diversi",
            status="codified",
            rate=rate,
            taxable_coefficient=sale_coefficient_titoli_stato,
            legal_reference=legal_reference,
        ),
        TaxTreatment(
            asset_class="titoli_stato_whitelist",
            event_kind="income",
            gain_category="redditi_capitale",
            loss_category="redditi_diversi",
            status="codified",
            rate=rate,
            taxable_coefficient=sale_coefficient_titoli_stato,
            legal_reference=legal_reference,
        ),
    )


_IT_2011_01 = TaxRuleset(
    code="IT-2011-01",
    valid_from=date(2000, 1, 1),
    valid_until=date(2012, 1, 1),
    # Aliquota generale 12,5% fino al 31/12/2011 (art. 5 D.Lgs. 461/1997);
    # i titoli di Stato erano gia' a 12,5% stabile, quindi qui coincide con
    # l'aliquota generale — nessun coefficiente necessario.
    treatments=_treatments(rate=Decimal("0.125"), legal_reference="D.Lgs. 461/1997 art. 5"),
    offset_rules=_OFFSET_RULES,
    carry_forward=_CARRY_FORWARD,
    lot_consumption_order="lifo",
)

_IT_2012_01 = TaxRuleset(
    code="IT-2012-01",
    valid_from=date(2012, 1, 1),
    valid_until=date(2014, 7, 1),
    # Aliquota generale 20% dal 1/1/2012 (DL 138/2011); titoli di Stato
    # whitelist restano a 12,5% per regime speciale, espresso qui come
    # aliquota diretta (nessun coefficiente: 12,5% e' gia' rappresentabile
    # senza ricorrere al trucco del DL 66/2014).
    treatments=_treatments(
        rate=Decimal("0.20"), legal_reference="DL 138/2011 conv. L. 148/2011",
    )[:5]
    + (
        TaxTreatment(
            asset_class="titoli_stato_whitelist",
            event_kind="sale",
            gain_category="redditi_diversi",
            loss_category="redditi_diversi",
            status="codified",
            rate=Decimal("0.125"),
            taxable_coefficient=Decimal("1"),
            legal_reference="DL 138/2011 art. 2 co. 31 (regime speciale titoli di Stato)",
        ),
        TaxTreatment(
            asset_class="titoli_stato_whitelist",
            event_kind="income",
            gain_category="redditi_capitale",
            loss_category="redditi_diversi",
            status="codified",
            rate=Decimal("0.125"),
            taxable_coefficient=Decimal("1"),
            legal_reference="DL 138/2011 art. 2 co. 31 (regime speciale titoli di Stato)",
        ),
    ),
    offset_rules=_OFFSET_RULES,
    carry_forward=_CARRY_FORWARD,
    lot_consumption_order="lifo",
)

_IT_2014_07 = TaxRuleset(
    code="IT-2014-07",
    valid_from=date(2014, 7, 1),
    valid_until=None,
    # Aliquota generale 26% dal 1/7/2014 (DL 66/2014); titoli di Stato
    # whitelist restano a tassazione effettiva 12,5% ma espressa come
    # aliquota generale (26%) per un coefficiente imponibile ridotto
    # (48,08%): 0.26 * 0.4808 = 0.125008 — coefficiente legale, non la
    # frazione esatta 12,5/26.
    treatments=_treatments(
        rate=Decimal("0.26"),
        legal_reference="DL 66/2014 art. 3",
        sale_coefficient_titoli_stato=Decimal("0.4808"),
    ),
    offset_rules=_OFFSET_RULES,
    carry_forward=_CARRY_FORWARD,
    loss_conversions=(
        LossConversion(
            formed_from=None,
            formed_until=date(2012, 1, 1),
            coefficient=Decimal("0.4808"),
            legal_reference="DL 66/2014 art. 3 co. 3 (minusvalenze formate fino al 31/12/2011)",
        ),
        LossConversion(
            formed_from=date(2012, 1, 1),
            formed_until=date(2014, 7, 1),
            coefficient=Decimal("0.7692"),
            legal_reference="DL 66/2014 art. 3 co. 3 (minusvalenze formate dal 1/1/2012 al 30/6/2014)",
        ),
    ),
    lot_consumption_order="lifo",
)

IT_RULESETS: tuple[TaxRuleset, ...] = (_IT_2011_01, _IT_2012_01, _IT_2014_07)
