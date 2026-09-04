"""Protocol `TaxJurisdiction` + dataclass puri della fiscalita' (SPEC_TAX_REGIME.md
FETTA 1). Nessuna dipendenza da DB/FastAPI — stessa natura di
`app/classification/taxonomy.py` e dei registri in `app/parsers/__init__.py`,
ma con una differenza sostanziale rispetto alle altre interfacce astratte di
CLAUDE.md (`BankParser`/`AIProvider`/`MarketDataProvider`, tutte I/O-bound con
profilo per-workspace e credenziali cifrate): `TaxJurisdiction` e' PURA e
SINCRONA. Nessun `async`, nessuna API key, nessuna tabella profilo — si
seleziona dalla residenza fiscale dell'anno (dato utente, vive in
`workspace_tax_residences`), non da una configurazione con credenziali.

Il regolamento fiscale vive qui come dato in codice, mai in DB — la legge non
e' dato utente, quindi nessuna tabella e nessuna divergenza possibile tra
motore e pagina informativa delle regole applicate.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

_CENTS = Decimal("0.01")


def quantize_money(amount: Decimal) -> Decimal:
    return amount.quantize(_CENTS, rounding=ROUND_HALF_UP)


class TaxRulesetNotFound(Exception):
    """Nessun ruleset vigente alla data richiesta — mai un fallback silenzioso
    (es. il primo/ultimo ruleset disponibile): significa che la data e'
    precedente all'entrata in vigore del regolamento modellato, un errore da
    segnalare, non da coprire con un numero inventato."""


@dataclass(frozen=True)
class AssetTaxRef:
    """Riferimento minimo di un asset per la derivazione della classe
    fiscale — sottoinsieme di `Asset`, cosi' `derive_asset_class` resta
    testabile senza costruire un ORM object."""

    asset_type: str
    isin: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class TaxAssetClass:
    """Una classe fiscale dichiarata dalla giurisdizione (es. `azioni`,
    `etf_armonizzato`, `obbligazioni`, `titoli_stato_whitelist`). `codified`
    a `False` significa che la classe esiste come dato (copertura totale
    dell'architettura, decisione di progetto) ma il motore non produce un
    numero per essa: l'asset viene escluso dal calcolo e segnalato."""

    code: str
    label_key: str
    codified: bool


@dataclass(frozen=True)
class TaxTreatment:
    """Trattamento fiscale di una classe asset per un tipo di evento
    realizzativo, in un dato ruleset. `gain_category`/`loss_category` sono
    campi DISTINTI apposta: e' qui che vive l'asimmetria dell'ETF
    armonizzato (plusvalenza -> `redditi_capitale`, minusvalenza ->
    `redditi_diversi`) senza un solo `if` nel motore di calcolo.

    `status="not_codified"` implica sempre `rate is None`: il motore non
    puo' produrre un numero neanche per errore su una categoria non
    verificata (cripto, derivati, ETF non armonizzati, certificati)."""

    asset_class: str
    event_kind: str
    gain_category: str
    loss_category: str
    status: str  # "codified" | "not_codified"
    rate: Decimal | None
    taxable_coefficient: Decimal
    legal_reference: str
    assumption: bool = False
    assumption_note: str | None = None

    def __post_init__(self) -> None:
        if self.status == "not_codified" and self.rate is not None:
            raise ValueError("un TaxTreatment not_codified non puo' avere un rate")
        if self.status == "codified" and self.rate is None:
            raise ValueError("un TaxTreatment codified deve avere un rate")
        if self.assumption and not self.assumption_note:
            raise ValueError("assumption=True richiede una assumption_note")


@dataclass(frozen=True)
class OffsetRule:
    """Coppia compensabile (loss_category, gain_category) — DEFAULT DENY:
    l'assenza di una regola significa non compensabile. La regola "una
    minusvalenza azionaria non compensa una plusvalenza ETF armonizzato"
    cade fuori da sola, perche' quella coppia non compare qui (il gain ETF
    e' `redditi_capitale`, mai `redditi_diversi`)."""

    loss_category: str
    gain_category: str


@dataclass(frozen=True)
class LossConversion:
    """Ricalibrazione dello stock di minusvalenze gia' accumulato quando
    cambia l'aliquota (precedente: DL 66/2014, 20%->26% dal 1/7/2014, con
    ricalibrazione retroattiva dello zainetto esistente). Vive sul
    regolamento CONSUMANTE, non su quello di formazione: applicata al
    momento dell'uso, mai riscrivendo lo storico. L'intervallo di formazione
    a cui si applica e' [formed_from, formed_until) — `formed_from=None`
    significa "da sempre"."""

    formed_from: date | None
    formed_until: date
    coefficient: Decimal
    legal_reference: str


@dataclass(frozen=True)
class CarryForwardRule:
    """Riporto pluriennale delle minusvalenze non ancora compensate.
    `years=4`, consumo FIFO per anno di formazione (art. 68 TUIR).
    `assumption=True`: il FIFO per anno di formazione e' prassi bancaria,
    non norma esplicita con questo dettaglio."""

    years: int
    assumption: bool = False
    assumption_note: str | None = None

    def __post_init__(self) -> None:
        if self.assumption and not self.assumption_note:
            raise ValueError("assumption=True richiede una assumption_note")


@dataclass(frozen=True)
class TaxRegimeOption:
    """Un regime ammesso dalla giurisdizione (es. amministrato,
    dichiarativo). "Amministrato/dichiarativo/gestito" e' vocabolario
    italiano — nessun enum globale, e' la giurisdizione a dichiarare quali
    codici sono ammissibili.

    `pocket_scope` decide la chiave del perimetro dello zainetto:
    `per_account` (amministrato: uno zainetto per intermediario) vs
    `aggregate` (dichiarativo: un unico zainetto personale, aggregato su
    tutti i conti). `calc_model` predispone il regime gestito (FETTA 1 non
    lo implementa, ma il modello non deve renderlo impossibile): `realized`
    tassa i singoli eventi di realizzo, `accrued` tasserebbe il risultato
    maturato a fine anno."""

    code: str
    label_key: str
    pocket_scope: str  # "per_account" | "aggregate"
    calc_model: str = "realized"  # "realized" | "accrued"


@dataclass(frozen=True)
class TaxRuleset:
    """Una versione del regolamento fiscale, vigente in [valid_from,
    valid_until). `valid_until=None` significa "tuttora vigente"."""

    code: str
    valid_from: date
    valid_until: date | None
    treatments: tuple[TaxTreatment, ...]
    offset_rules: tuple[OffsetRule, ...]
    carry_forward: CarryForwardRule
    loss_conversions: tuple[LossConversion, ...] = field(default_factory=tuple)

    def treatment_for(self, asset_class: str, event_kind: str) -> TaxTreatment | None:
        for t in self.treatments:
            if t.asset_class == asset_class and t.event_kind == event_kind:
                return t
        return None

    def can_offset(self, loss_category: str, gain_category: str) -> bool:
        return any(
            r.loss_category == loss_category and r.gain_category == gain_category
            for r in self.offset_rules
        )

    def conversion_for(self, formation_date: date) -> LossConversion | None:
        for c in self.loss_conversions:
            if formation_date < c.formed_until and (c.formed_from is None or formation_date >= c.formed_from):
                return c
        return None


@dataclass(frozen=True)
class UsableLoss:
    """Esito dell'applicazione di una eventuale `LossConversion` a una
    minusvalenza nominale, al momento dell'uso in un dato ruleset. Il
    nominale originale non viene mai mutato: solo il risultato riporta la
    conversione applicata (o l'assenza di conversione, coefficiente 1)."""

    nominal: Decimal
    coefficient: Decimal
    usable_amount: Decimal
    conversion_reference: str | None


class TaxJurisdiction(Protocol):
    """Interfaccia astratta (CLAUDE.md: BankParser/AIProvider/
    MarketDataProvider/TaxJurisdiction) — unica implementazione in FETTA 1:
    `ItalyTaxJurisdiction`. Pura e sincrona: non calcola lo zainetto (quello
    e' `tax_calc.py`, guidato dal ruleset che riceve come argomento), non
    tocca il DB, non decide in che regime sia un conto — dichiara solo quali
    codici sono ammissibili e a quale ruleset appartiene una data."""

    code: str
    label_key: str

    def rulesets(self) -> tuple[TaxRuleset, ...]: ...

    def ruleset_at(self, on: date) -> TaxRuleset: ...

    def regimes(self, on: date) -> tuple[TaxRegimeOption, ...]: ...

    def tax_asset_classes(self, on: date) -> tuple[TaxAssetClass, ...]: ...

    def derive_asset_class(self, ref: AssetTaxRef, on: date) -> str | None: ...

    def treatment(self, asset_class: str, event_kind: str, on: date) -> TaxTreatment | None: ...

    def can_offset(self, loss_category: str, gain_category: str, on: date) -> bool: ...

    def usable_loss(self, nominal: Decimal, formation_date: date, on: date) -> UsableLoss: ...
