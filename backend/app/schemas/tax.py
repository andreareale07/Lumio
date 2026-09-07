"""Schemi Pydantic per l'API fiscale (SPEC_TAX_REGIME.md FETTA 1).

I dataclass di `app/tax/base.py` sono rispecchiati 1:1 (nessun rimodellamento,
solo `*_key` gia' presenti per l'i18n) — e' cio' che rende impossibile alla
pagina informativa delle regole di divergere da quanto realmente applicato
dal motore."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TaxJurisdictionOut(BaseModel):
    code: str
    label_key: str


class TaxRegimeOptionOut(BaseModel):
    code: str
    label_key: str
    pocket_scope: str
    calc_model: str


class TaxAssetClassOut(BaseModel):
    code: str
    label_key: str
    codified: bool


class TaxTreatmentOut(BaseModel):
    asset_class: str
    event_kind: str
    gain_category: str
    loss_category: str
    status: str
    rate: Decimal | None
    taxable_coefficient: Decimal
    legal_reference: str
    assumption: bool
    assumption_note: str | None


class OffsetRuleOut(BaseModel):
    loss_category: str
    gain_category: str


class LossConversionOut(BaseModel):
    formed_from: date | None
    formed_until: date
    coefficient: Decimal
    legal_reference: str


class CarryForwardRuleOut(BaseModel):
    years: int
    assumption: bool
    assumption_note: str | None


class TaxRulesetSummaryOut(BaseModel):
    code: str
    valid_from: date
    valid_until: date | None


class TaxRulesetDetailOut(TaxRulesetSummaryOut):
    treatments: list[TaxTreatmentOut]
    offset_rules: list[OffsetRuleOut]
    carry_forward: CarryForwardRuleOut
    loss_conversions: list[LossConversionOut]
    # Non parte del dataclass TaxRuleset (vivono su TaxJurisdiction, sono
    # anch'essi funzione della data) — inclusi qui perche' questo e' l'unico
    # endpoint "pagina informativa" del regolamento: evita di inventare due
    # endpoint separati per due liste che servono solo a popolare i picker
    # della UI (creazione periodo di regime, override classificazione asset).
    regimes: list[TaxRegimeOptionOut]
    asset_classes: list[TaxAssetClassOut]


# --- Residenza fiscale -------------------------------------------------------


class WorkspaceTaxResidenceIn(BaseModel):
    fiscal_year: int = Field(ge=1900, le=9999)
    jurisdiction_code: str


class WorkspaceTaxResidenceOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    fiscal_year: int
    jurisdiction_code: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Periodi di regime del conto ---------------------------------------------


class TaxRegimePeriodCreate(BaseModel):
    regime_code: str
    effective_from: date


class TaxRegimePeriodUpdate(BaseModel):
    regime_code: str | None = None
    effective_from: date | None = None


class TaxRegimePeriodOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    financial_account_id: uuid.UUID
    regime_code: str
    effective_from: date
    created_at: datetime

    model_config = {"from_attributes": True}


class TaxRegimeResolveOut(BaseModel):
    regime_code: str | None


# --- Classificazione fiscale asset -------------------------------------------


class AssetTaxClassificationOut(BaseModel):
    asset_id: uuid.UUID
    asset_class: str | None
    is_override: bool
    codified: bool


class AssetTaxClassificationSetIn(BaseModel):
    asset_class: str


# --- Saldi di apertura zainetto ----------------------------------------------


class TaxLossOpeningCreate(BaseModel):
    # Obbligatorio-ma-nullable: il client DEVE inviare esplicitamente il
    # campo (None per il perimetro dichiarativo aggregato, un id per quello
    # amministrato) — mai un default preselezionato, coerente con la UI
    # (dialog senza perimetro precompilato).
    financial_account_id: uuid.UUID | None
    formation_date: date
    income_category: str
    amount: Decimal


class TaxLossOpeningUpdate(BaseModel):
    formation_date: date | None = None
    income_category: str | None = None
    amount: Decimal | None = None


class TaxLossOpeningOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    financial_account_id: uuid.UUID | None
    formation_date: date
    formed_under_ruleset_code: str
    income_category: str
    amount: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Zainetto ------------------------------------------------------------


class LossPocketRowOut(BaseModel):
    formation_date: date
    nominal: Decimal
    income_category: str
    perimeter: str
    source: str
    formed_under_ruleset_code: str
    applied_ruleset_code: str
    coefficient: Decimal
    usable_amount: Decimal
    conversion_reference: str | None
    expires_on: date
    is_expired: bool
    # None per le aperture manuali (saldo aggregato, non legato a un
    # titolo) — valorizzato per le righe "computed" (FETTA 2).
    asset_id: uuid.UUID | None = None
    # Capacita' REALE rimasta DOPO la compensazione progressiva delle
    # plusvalenze (FETTA 2) — `usable_amount` sopra resta il valore grezzo
    # mai mutato (audit); questo e' "quanto ne resta da usare davvero",
    # <= usable_amount sempre, 0 se completamente consumata.
    remaining_amount: Decimal


class ExcludedRealizedEventOut(BaseModel):
    """Un evento realizzativo (vendita reale) che NON entra nello zainetto
    — mai un numero inventato per un asset non codificato o un conto senza
    regime a quella data (SPEC_TAX_REGIME.md FETTA 2, "copertura parziale")."""

    financial_account_id: uuid.UUID
    asset_id: uuid.UUID
    trade_date: date
    gain_or_loss: Decimal
    excluded_reason: str


class LossPocketOut(BaseModel):
    rows: list[LossPocketRowOut]
    # Totale GREZZO per perimetro, mai toccato dalla compensazione (audit).
    totals_by_perimeter: dict[str, Decimal]
    # Capacita' REALE rimasta per perimetro DOPO la compensazione delle
    # plusvalenze — questo e' il numero da mostrare come "capienza
    # disponibile" in UI (scelta dell'utente in QA: il totale grezzo da
    # solo confondeva, sembrava capienza libera quando non lo era piu').
    remaining_by_perimeter: dict[str, Decimal]
    residence_declared: bool
    # FETTA 2: True quando almeno una riga viene dal motore a lotti
    # (source="computed"), non solo da aperture manuali.
    computed_from_movements: bool = False
    excluded_events: list[ExcludedRealizedEventOut] = Field(default_factory=list)


class TaxableGainRowOut(BaseModel):
    trade_date: date
    perimeter: str
    gain_category: str
    nominal: Decimal
    offset_amount: Decimal
    taxable_amount: Decimal
    tax_due: Decimal
    asset_id: uuid.UUID
    lot_transaction_id: uuid.UUID
    sell_transaction_id: uuid.UUID


class TaxableGainsOut(BaseModel):
    rows: list[TaxableGainRowOut]
    tax_due_by_perimeter: dict[str, Decimal]
    remaining_pocket_by_perimeter: dict[str, Decimal]
    excluded_events: list[ExcludedRealizedEventOut] = Field(default_factory=list)


# --- Eventi realizzati + override per singolo evento (FETTA 2) --------------


class ClassifiedRealizedEventOut(BaseModel):
    """Rispecchia `ClassifiedRealizedEvent` 1:1 — un evento e' identificato
    dalla coppia `(lot_transaction_id, sell_transaction_id)`, univoca per
    costruzione (mai una sola data, ambigua con piu' movimenti stesso
    giorno)."""

    financial_account_id: uuid.UUID
    asset_id: uuid.UUID
    trade_date: date
    quantity: Decimal
    proceeds: Decimal
    cost_basis: Decimal
    gain_or_loss: Decimal
    lot_formation_date: date
    lot_transaction_id: uuid.UUID
    sell_transaction_id: uuid.UUID
    asset_class: str | None
    gain_category: str | None
    loss_category: str | None
    rate: Decimal | None
    taxable_coefficient: Decimal | None
    legal_reference: str | None
    perimeter: str | None
    formed_under_ruleset_code: str | None
    excluded_reason: str | None
    is_overridden: bool


class RealizedEventsPageOut(BaseModel):
    """Pagina filtrata/ordinata sopra `list_realized_events` (già calcolato
    per intero in memoria, nessuna query paginata a DB) — `total` è un
    conteggio esatto post-filtro, non un'euristica basata sul riempimento
    della pagina."""

    items: list[ClassifiedRealizedEventOut]
    total: int


class TaxEventOverrideIn(BaseModel):
    override_gain_or_loss: Decimal | None = None
    excluded: bool = False
    notes: str | None = None


class TaxEventOverrideOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    lot_transaction_id: uuid.UUID
    sell_transaction_id: uuid.UUID
    override_gain_or_loss: Decimal | None
    excluded: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
