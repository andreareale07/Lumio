## Task: implementare FETTA 1 della fiscalità italiana dei conti titoli

Le decisioni di progetto sono chiuse (studio, ricerca normativa e design frontend/backend già
fatti in una sessione precedente). Questo documento **non è più un prompt di studio**: è il
brief operativo, autosufficiente, per implementare FETTA 1. Se qualcosa qui sotto non è
chiaro o sembra in conflitto col codice reale, fermati e segnala `DECISION REQUIRED` — non
improvvisare sopra decisioni normative (vedi §Assunzioni fiscali in fondo).

Obiettivo di FETTA 1: Lumio deve rispondere in modo deterministico e auditabile a "quanto
zainetto fiscale ho, formato quando, che scade quando, e perché quel numero è quel numero" —
per **regime amministrato** (per intermediario) e **regime dichiarativo** (aggregato
personale). Il motore che deriva lo zainetto dai movimenti (lotti LIFO, eventi realizzativi)
è **FETTA 2**, fuori scope qui: in FETTA 1 lo zainetto è alimentato solo da saldi di apertura
inseriti a mano dall'utente.

### Perché (caso reale dell'utente)

Un conto Trade Republic è nato con IBAN tedesco in **regime dichiarativo** (TR non aveva
stabile organizzazione italiana, non poteva fare da sostituto d'imposta) ed è diventato
**regime amministrato** quando TR ha attivato l'IBAN italiano. Lo stesso conto ha quindi
attraversato due regimi nel tempo. In amministrato, l'ordine delle vendite conta: vendere le
posizioni in perdita prima di quelle in profitto fa compensare la minusvalenza contro la
plusvalenza **prima** che questa generi imposta; l'ordine inverso non recupera l'imposta già
prelevata. Lumio oggi non ha alcun concetto che permetta di ragionarci (zero occorrenze di
`regime`, `plusvalenza`, `minusvalenza`, `zainetto` nel backend).

---

## Decisioni di progetto (non rimetterle in discussione)

1. **Multi-giurisdizione per interfaccia.** La residenza fiscale è della persona, non del
   conto (e nemmeno lei basta sempre: cittadinanza USA, ritenuta alla fonte, art. 24-bis TUIR
   — fuori scope, ma è perché la residenza da sola non è un modello sufficiente che si passa
   per un'interfaccia). Interfaccia `TaxJurisdiction` accanto a `BankParser`/`AIProvider`/
   `MarketDataProvider` (regola non negoziabile di `CLAUDE.md`), con `ItalyTaxJurisdiction`
   unica implementazione. "Amministrato/dichiarativo/gestito" è vocabolario italiano:
   **nessun enum globale**, i regimi ammessi li dichiara la giurisdizione.
2. **Regole fiscali versionate nel tempo, come dato puro in codice.** Precedente normativo:
   il DL 66/2014 non ha solo cambiato l'aliquota da 20% a 26% dal 1/7/2014, ha **riscalato lo
   stock di zainetto già accumulato** (usabile al 48,08% se formato entro il 2011, al 76,92%
   se formato dal 2012 al 30/6/2014). Quindi lo zainetto memorizza la **data** di formazione
   (non l'anno: il taglio era a metà anno) e la conversione si applica **al momento dell'uso**,
   mai riscrivendo lo storico.
3. **Pagina informativa delle regole applicate**, letta dalla stessa struttura dati che
   alimenta il motore — non può quindi divergere da ciò che viene realmente applicato.
4. **Copertura**: l'architettura (categorie fiscali, aliquote, matrice di compensabilità,
   coefficienti) copre tutto fin da subito ed è solo dato. In v1 si codificano e testano solo
   le regole verificate su fonti solide: azioni, ETF armonizzati, obbligazioni, titoli di
   Stato whitelist. Una categoria non codificata (cripto, derivati, ETF non armonizzati,
   certificati) **non deve produrre un numero**: l'asset è escluso dal calcolo e segnalato.
5. **Un conto solo per il caso Trade Republic**, con due periodi di regime — non due conti.
   La catena LIFO dei lotti resta continua (FETTA 2), `positions` resta unica su
   `(workspace, conto, asset)`, lo storico IBAN esiste già
   ([financial_account_iban_history.py](backend/app/models/financial_account_iban_history.py)).
   Il perimetro fiscale si risolve **per evento**, dalla sua data — non è una proprietà fissa
   del conto.
6. **Calcolato + override manuale**, con distinzione visibile ("calcolato" vs "inserito
   dall'utente"). Saldi di apertura per anno di formazione **obbligatori**: lo storico
   dell'utente in Lumio copre solo una piccola parte del periodo reale (oltre due anni, cambio
   IBAN già avvenuto), quindi i lotti anteriori non sono ricostruibili.
7. **Consegna a fette verticali.** Questo documento è **FETTA 1**.

Decisioni minori già risolte (reversibili, nessun impatto su schema — non riaprirle senza
motivo): default di classificazione ETF = derivato solo con segnale forte (`asset_type="etf"`
**e** ISIN che comincia per `IE`/`LU` **e** nome contiene `UCITS`), altrimenti
`unclassified`; router fiscale dedicato (`app/api/v1/tax.py`) invece di sotto-risorsa di
`accounts`; `quantize_money` locale in `app/tax/base.py` invece di un `app/core/money.py`
cross-cutting; whitelist titoli di Stato ad assegnazione manuale in FETTA 1 (non derivata da
lista paesi); chiusura d'anno (`tax_year_closures`) rimandata a FETTA 2, non a FETTA 3.

---

## Architettura

```
Investment Transactions  ──┬──▶  Portfolio Valuation      (costo medio mobile, INTATTO)
                           │
                           └──▶  Fiscal Engine  ──▶ Fiscal UI
```

Due vincoli non negoziabili:

- **`position_calc.py` non si tocca.** Il costo medio ponderato mobile resta la
  valorizzazione (SPEC §34). Il motore fiscale (FETTA 2) sarà un modulo parallelo che riusa il
  `Protocol MovementLike` ([position_calc.py:28](backend/app/services/position_calc.py:28)) ma
  **non deve** ereditare la conflazione `fees + tax` delle righe 89 e 104: fiscalmente `fees`
  è onere accessorio (entra nel costo del lotto), `tax` è imposta già prelevata (un esito, mai
  una componente di costo). Non riguarda FETTA 1 (che non calcola dai movimenti), ma va tenuto
  a mente progettando `LossPocketEntry` per non chiudere la porta.
- **Il regolamento vive in codice, non in DB.** Stessa natura di
  [taxonomy.py](backend/app/classification/taxonomy.py), ma senza seed: la legge non è dato
  utente, quindi nessuna tabella e nessuna divergenza possibile.

Il **regime gestito** non si implementa in questa fetta, ma il modello non deve renderlo
impossibile: a differenza di amministrato/dichiarativo tassa il risultato **maturato** a fine
anno (non i singoli realizzi), il perimetro è il singolo contratto, e i redditi di capitale
**sono** compensabili al suo interno — l'opposto dell'amministrato. Per questo un regime deve
poter dichiarare il proprio modello di calcolo, non solo il proprio perimetro.

---

## Backend

### Dato puro (nessuna dipendenza DB — implementare e testare PRIMA dei modelli)

```
backend/app/tax/base.py            Protocol TaxJurisdiction + dataclass frozen + quantize_money
backend/app/tax/registry.py        JURISDICTIONS + get_jurisdiction(code)   (stessa forma di app/parsers/__init__.py:33)
backend/app/tax/jurisdictions/italy.py
backend/app/tax/rulesets/italy.py  IT_RULESETS — unica fonte di verità
```

Dataclass chiave (nomi indicativi, seguire le convenzioni del repo):

- **`TaxTreatment`**: `gain_category` e `loss_category` come **campi distinti** — è qui che
  vive l'asimmetria ETF armonizzato (gain → `redditi_capitale`, loss → `redditi_diversi`)
  senza un solo `if` nel motore. Con `status="not_codified"` → `rate is None`: il motore non
  può produrre un numero neanche per errore.
- **`OffsetRule`**: coppie `(loss_category, gain_category)`, **default deny** — assenza di
  regola = non compensabile. La regola "una minusvalenza su azione non compensa una
  plusvalenza su ETF armonizzato" cade fuori da sola, perché quella coppia non esiste (il gain
  ETF è `redditi_capitale`, non `redditi_diversi`).
- **`LossConversion`**: vive sul regolamento **consumante**, non su quello di formazione.
  Conseguenza: lo storico non si riscrive mai; una minusvalenza 2013 usata nel marzo 2014
  (prima del 1/7) non subisce conversione, senza bisogno di casi speciali.
- **`CarryForwardRule`**: `years=4`, consumo FIFO per anno di formazione — marcata
  `assumption=True` (fonte debole, prassi bancaria più che norma esplicita).

Tre versioni di `IT_RULESETS`: `IT-2011-01` (12,5%), `IT-2012-01` (20%), `IT-2014-07` (26%,
coefficiente 48,08% sui titoli di Stato whitelist, più le due `LossConversion` del DL
66/2014: 48,08% per formazione ≤ 31/12/2011, 76,92% per formazione 1/1/2012–30/6/2014).

⚠️ `0.26 × 0.4808 = 0.125008`, non 12,5% esatti — sono i coefficienti *legali*, non la
frazione 12,5/26. Il test di invariante va con tolleranza `1e-5`; non "correggere" i
letterali sostituendoli con `Decimal("12.5")/Decimal("26")`.

`TaxJurisdiction` è **pura e sincrona** — differenza sostanziale dalle altre tre interfacce di
`CLAUDE.md`, che sono I/O-bound con profilo per-workspace e credenziali cifrate. Nessun
`async`, nessuna API key, nessuna tabella profilo: si seleziona dalla residenza fiscale
dell'anno, non da una configurazione dell'utente. Non calcola lo zainetto (quello è
`tax_calc.py`, guidato dal ruleset che riceve come argomento), non tocca il DB, non decide in
che regime sia un conto — dichiara solo quali codici sono ammissibili.

Firma minima:
```
class TaxJurisdiction(Protocol):
    code: str
    label_key: str
    def rulesets(self) -> tuple[TaxRuleset, ...]
    def ruleset_at(self, on: date) -> TaxRuleset          # solleva TaxRulesetNotFound, mai un fallback silenzioso
    def regimes(self, on: date) -> tuple[TaxRegimeOption, ...]
    def tax_asset_classes(self, on: date) -> tuple[TaxAssetClass, ...]
    def derive_asset_class(self, ref: AssetTaxRef, on: date) -> str | None
    def treatment(self, asset_class: str, event_kind: str, on: date) -> TaxTreatment | None
    def can_offset(self, loss_category: str, gain_category: str, on: date) -> bool
    def usable_loss(self, nominal: Decimal, formation_date: date, on: date) -> UsableLoss
```

### Tabelle (4, migration `0039_tax_domain.py`, `down_revision = "0038_import_account_after_upload"`)

| Tabella | Chiave del design |
|---|---|
| `workspace_tax_residences` | **Append-only per anno di decorrenza** (deciso dopo il rilascio di FETTA 1, stesso pattern minimo di `financial_account_tax_regimes`): una riga `(fiscal_year=2015, jurisdiction=CH)` vale da quell'anno finché non arriva un cambiamento successivo, non solo per quell'anno esatto — l'utente imposta la residenza **una volta** e resta valida, storico multi-periodo aggiungendo più righe (`2010 IT`, `2015 CH`, `2020 IT`). `UniqueConstraint(workspace_id, fiscal_year)` invariato; granularità **anno**, mai una data esatta, perché l'Italia non ha split-year (si è residenti per l'intero anno solare). Risoluzione in `tax_context.resolve_tax_context`: riga con `fiscal_year` più recente ≤ l'anno richiesto. |
| `financial_account_tax_regimes` | Append-only con `effective_from`, **niente `valid_to`**: l'intervallo di una riga è `[effective_from, next.effective_from)`, risolto a lettura ordinando per `effective_from`. Sovrapposizioni impossibili per costruzione — nessun `EXCLUDE`/`btree_gist`. `regime_code` senza CHECK enum, validato al confine applicativo contro `jurisdiction.regimes(effective_from)`. |
| `asset_tax_classifications` | Riga **solo** se l'utente sovrascrive il default derivato. Non su `assets` (concetto giurisdizione-specifico in un catalogo neutro) né su `asset_profiles` (cache con TTL 30gg che si rigenera, perderebbe l'override). Chiave `(workspace_id, asset_id, jurisdiction_code)`. |
| `tax_loss_opening_balances` | `formation_date` (data, non anno) + `formed_under_ruleset_code` (timbro di audit scritto dal server risolvendo `formation_date`, mai dal client). `amount` è il **nominale**, mai convertito. `financial_account_id` **nullable**, valorizzato sse il regime ha perimetro per-intermediario, NULL per il perimetro personale/aggregato — due indici UNIQUE parziali per l'unicità (uno con `WHERE financial_account_id IS NOT NULL`, uno `WHERE ... IS NULL`). |

Il pattern `valid_from`/`valid_to` **non esiste nel repo e qui non va introdotto** — l'unica
entità storicizzata esistente,
[financial_account_iban_history.py](backend/app/models/financial_account_iban_history.py), è
append-only senza intervalli; il pattern `effective_from` sopra ne è l'estensione minima.

RLS obbligatoria su tutte e 4: `ENABLE` + `FORCE ROW LEVEL SECURITY` e **4 policy separate**
(select/insert/update/delete) con `is_workspace_member(workspace_id)`, mai `FOR ALL` — loop
identico a `0033_transaction_dedup.py:313-340`. FK composite `(workspace_id, fk_id)` verso
`(parent.workspace_id, parent.id)`; `financial_accounts` e `assets` hanno già il
`UniqueConstraint(workspace_id, id)` richiesto, nessuna ALTER sui genitori. `downgrade()`:
`DROP POLICY IF EXISTS` × 16 prima dei 4 `drop_table`, in ordine inverso.

Vincolo `regime_code` ↔ presenza di `financial_account_id` **non esprimibile in DB** (dipende
da dato in codice, il `pocket_scope` del regime): enforced in `tax_opening_service.py` con 400
esplicito, documentato nella docstring della migration.

### Servizi

```
backend/app/services/tax_context.py              resolve_tax_context(db, ws, on) -> TaxContext
backend/app/services/tax_regime_service.py        CRUD periodi + resolve_regime_at(account, date)
backend/app/services/tax_classification_service.py  override + derivazione + elenco "non codificati"
backend/app/services/tax_opening_service.py       CRUD aperture + validazione perimetro/regime
backend/app/services/tax_calc.py                  PURO: build_loss_pocket(entries, ruleset, on)
```

Se manca la residenza per l'anno richiesto, usare il default `IT` (config
`tax_default_jurisdiction`) **con `residence_declared=False` propagato fino alla response**,
così la UI può dire "residenza non dichiarata, mostro le regole italiane" invece di far finta
di saperlo.

`build_loss_pocket` prende una lista di `LossPocketEntry` (dataclass pura: `formation_date`,
`nominal`, `income_category`, `perimeter`, `source`). In FETTA 1 la lista viene **solo** dalle
aperture manuali; in FETTA 2 sarà `aperture + eventi realizzativi`, senza modificare questa
funzione.

### Derivato, non persistito

Lo zainetto si deriva a lettura ogni volta; si persistono solo gli input (residenze, periodi,
override, aperture) — tutti dati utente non ricostruibili. Precedente decisivo già nel repo:
[portfolio_analytics.py:654](backend/app/services/portfolio_analytics.py:654)
(`compute_historical_series`) ha abbandonato lo snapshot congelato proprio perché l'utente
corregge e retrodata i movimenti — un motore fiscale che congelasse i numeri produrrebbe la
stessa divergenza silenziosa.

L'auditabilità non si ottiene congelando i numeri, ma rendendo ogni numero spiegabile: ogni
riga della vista zainetto restituisce `formed_under_ruleset_code`, `applied_ruleset_code`,
`coefficient`, `conversion_reference`, `expires_on`, `source`, più un blocco `excluded` con il
motivo per gli asset fuori calcolo.

Unica eccezione futura (**non costruire ora**, solo lasciare scritto nella docstring di
`tax_calc.py`): la chiusura d'anno (`tax_year_closures`, FETTA 2) — una volta presentato il
quadro RT, il numero dichiarato va congelato e non deve più muoversi con correzioni successive
ai movimenti.

### Endpoint (`backend/app/api/v1/tax.py`, prefix `/tax`, registrato in `router.py`)

```
GET    /tax/jurisdictions
GET    /tax/rulesets
GET    /tax/ruleset?on=YYYY-MM-DD                          # pagina informativa — vigente in quella data
GET|PUT|DELETE  /tax/residences[/{fiscal_year}]
GET|POST|PATCH|DELETE  /tax/accounts/{account_id}/regimes[/{id}]
GET    /tax/regimes/resolve?account_id=&on=
GET    /tax/asset-classifications
PUT|DELETE  /tax/asset-classifications/{asset_id}
GET|POST|PATCH|DELETE  /tax/loss-pocket/openings[/{id}]
GET    /tax/loss-pocket?on=YYYY-MM-DD                       # computed_from_movements: false in FETTA 1
```

`schemas/tax.py` rispecchia i dataclass **1:1** (nessun rimodellamento, solo `*_key` per la
i18n) — è ciò che rende impossibile alla pagina informativa di divergere dal motore. Ogni
query filtra esplicitamente per `workspace_id` oltre alla RLS. Gotcha ricorrente del progetto:
`SET LOCAL app.current_user_id` scade al commit — nessuna lettura dopo `db.commit()` sulla
stessa sessione.

### File da modificare (oltre a quelli nuovi)

`app/models/__init__.py` (+4 import/`__all__`) · `app/api/v1/router.py` (+router `tax`) ·
`tests/conftest.py` (+4 tabelle nel `TRUNCATE ... CASCADE`, righe 69-78 — omissione classica
che fa fallire test in ordine casuale) · `app/core/config.py`
(`tax_default_jurisdiction: str = "IT"`) · `app/models/audit_log.py`
(`EVENT_TYPES += ("TAX_SETTING_CHANGED",)`, con relativo `DROP`/`ADD CONSTRAINT` nella
migration).

**Esplicitamente da NON toccare**: `position_calc.py`, `position_service.py`, `asset.py`,
`asset_matching.py`, `asset_profile.py`, `investment_transaction.py`. Zero rischio sui 7 call
site di `recompute_position`.

### Ordine di implementazione

1. `tax/base.py` → 2. `tax/rulesets/italy.py` → 3. `tax/jurisdictions/italy.py` +
   `registry.py` → 4. **test invarianti sul dato e sulla giurisdizione** (nessun DB) → 5.
   `tax_calc.py` + test (nessun DB) → 6. modelli + `models/__init__.py` + migration +
   `conftest.py` → 7. `test_rls_tax.py` → 8. servizi → 9. schemi + API + router + config → 10.
   `test_tax_api.py`.

I punti 1-5 non toccano il DB: se qualcosa nel design va rivisto, si scopre lì, prima della
migration.

---

## Frontend

Nuova feature dir `frontend/src/features/tax/` — la fiscalità attraversa accounts, portfolio
e settings; metterla in una delle tre invertirebbe l'accoppiamento.

| Funzionalità | Collocazione |
|---|---|
| Periodi di regime (scrittura) | Sezione su `AccountEditPage.tsx`, sotto `IbanHistorySection` (stesso problema di forma, stesso motivo per cui quella pagina esiste). **`AccountForm.tsx` non si tocca**: il regime è una collezione temporale, non un campo scalare, e in creazione non c'è ancora un conto a cui appenderlo. |
| Periodi (lettura) + zainetto del conto | 4° tab "Fiscalità" su `AccountDetailPage.tsx` + badge del regime corrente nell'header. |
| Residenza fiscale + regole applicate | Nuova pagina Settings `/settings/tax`, due tab (`?tab=config`, `?tab=rules`), gruppo `finance` di `settingsNav.ts`. Granularità **anno**, mai un date picker — suggerirebbe uno split-year che in Italia non esiste. Lista mostrata come **intervalli** (`2010 → 2014: Italia`, `2015 → 2019: Svizzera`, `2020 → oggi: Italia`), non un elenco anno-per-anno: coerente con la semantica append-only del dato (vedi tabella `workspace_tax_residences` sopra). |
| Classificazione fiscale asset | `AssetTaxCard` autonoma su `AssetDetailPage.tsx` — **non** dentro `AssetInfoCard` (che fa `return null` quando manca il profilo arricchito): la classificazione fiscale deve essere sempre visibile. |
| Saldi di apertura zainetto | Dialog dentro la vista zainetto. Il perimetro è un campo **obbligatorio, senza valore preselezionato** — le fonti si contraddicono su cosa succede alle minusvalenze passando da dichiarativo ad amministrato, quindi Lumio non decide al posto dell'utente. |
| Zainetto amministrato + dichiarativo | Nuova pagina `/investments/tax`, due sezioni. **Nessun totale cross-perimetro** — mai sommare amministrato e dichiarativo. Il dichiarativo elenca esplicitamente (chip cliccabili) i conti che lo compongono. |

Entry point da `InvestmentsOverviewPage.tsx` e dal tab del conto — **nessuna voce nuova in
`NAV_SECTIONS`** (la sidebar è stata appena ridotta per decisione di `SPEC_FE_REDESIGN.md`
§45: *gerarchia*/*progressive disclosure* sopra il tutto-visibile).

### i18n

Nuovo namespace `tax` (il 15°) in `frontend/src/locales/{it,en}/tax.json` + registrazione in
`app/i18n.ts`, più chiavi in `enums.json` (`taxRegime`, `taxAssetClassification`,
`taxIncomeCategory`, `taxJurisdiction`), `settings.json`, `accounts.json`.

I regimi **non sono un enum frontend**: `useTaxRegimeLabel(code)` ritorna
`{label, isTranslated}` con `t('enums:taxRegime.'+code, {defaultValue:''})`; se la chiave
manca, mostrare il codice in `font-mono` con un badge "non tradotto" — mai una stringa
snake_case travestita da etichetta. Stesso trattamento per classificazioni asset e categorie
di reddito. `types/api.ts`: **nessun array `as const`** per regimi/classificazioni (sono
liste dichiarate dal backend, non enum frontend) — a differenza di `ACCOUNT_TYPES`/
`ASSET_TYPES` esistenti.

### Linguaggio visivo

Principio guida: un numero presentato con troppa sicurezza è un danno. Nessun numero fiscale
compare nudo. Componenti reali da riusare (verificati, non da inventare):
`frontend/src/components/ui/{Badge,Card,EmptyState,ErrorState,Skeleton,Dialog,Tabs,LinkButton,BackLink}.tsx`.
`Badge` ha i toni `neutral|primary|success|warning|danger`
([Badge.tsx](frontend/src/components/ui/Badge.tsx)); le classi monetarie/di segno
(`text-success`, `text-danger`, `text-text-muted`, `font-numeric`) sono le stesse già usate in
[AssetDetailPage.tsx](frontend/src/features/portfolio/AssetDetailPage.tsx) per il P&L.

- **Mai verde sullo zainetto**: un totale grande significa che hai perso molti soldi. Resta
  `text-text` neutro, etichettato "capienza disponibile" — deviazione intenzionale dalla
  convenzione P&L, non un'invenzione.
- **`expires_on` lo calcola il backend, sempre.** La regola "anno Y → 31/12/Y+4" vive nel
  regolamento versionato; se il frontend la ricalcola, la pagina regole e il numero mostrato
  possono divergere in silenzio — il fallimento peggiore possibile in questo dominio.
- **Copertura parziale ⇒ il totale non è definitivo**: `TaxCoverageNotice` (tono `warning`,
  non `danger`: non è un errore dell'app) sopra ogni vista con totali, prefisso "almeno" sulla
  cifra, elenco espandibile degli asset esclusi con link diretti.
- **Scadenze**: escalation testuale prima che cromatica (la distanza temporale è sempre
  scritta, mai solo un colore), mai rosso — non è un errore, è una data.
- Su mobile la matrice di compensazione a 375px diventa una lista di frasi, non una tabella
  che scorre in orizzontale.

### Quattro empty state distinti sulla vista zainetto (`/investments/tax`)

1. **Nessun regime impostato su nessun conto** → non mostrare zero, spiegare che lo zainetto
   non ha senso senza un perimetro e rimandare a `/settings/tax`.
2. **Regime impostato, nessun saldo e nessun calcolo** (stato di default al rilascio) →
   empty state onesto: *"Lumio non calcola ancora le minusvalenze dai movimenti. Se ne hai di
   pregresse, inseriscile come saldo di apertura."* — dire esplicitamente che l'assenza del
   numero è un limite di Lumio, non un fatto fiscale (altrimenti l'utente conclude di non
   avere minusvalenze).
3. **Saldi presenti** → card per perimetro; un pool a residuo 0 dopo consumo mostra "0,00 €"
   con nota "capienza esaurita", non collassa nell'empty state.
4. **Copertura parziale** → `TaxCoverageNotice` sopra le card, totali marcati parziali.

### Ordine di implementazione

0. tipi + `features/tax/api.ts` + `labels.ts` + namespace i18n → 1. Settings tab config → 2.
   **tab Regole** (read-only, anticipato: senza fonte visibile, ogni cifra mostrata dopo è
   un'affermazione senza prova) → 3. regime sul conto (Trade Republic è il caso di test
   canonico: due periodi consecutivi) → 4. classificazione asset → 5. zainetto e aperture → 6.
   tab conto + entry point → 7. copertura, tono, responsive.

---

## Test

**Backend**
- `test_tax_rulesets.py` — copertura temporale contigua e senza sovrapposizioni tra le 3
  versioni; ogni `treatment` codificato ha `rate` e `legal_reference`; ogni `not_codified` ha
  **`rate is None`**; ogni `assumption=True` ha una nota col marker
  `FISCAL ASSUMPTION REQUIRING VALIDATION`; `rate × taxable_coefficient ≈ 0.125` con tolleranza
  `1e-5` sotto `IT-2014-07`.
- `test_tax_jurisdiction.py` — confine 1/7/2014 (`ruleset_at` cambia versione esattamente lì);
  conversioni 48,08%/76,92% e nessuna conversione fuori tempo; **asimmetria ETF armonizzato**
  esplicita; `can_offset("redditi_diversi","redditi_capitale") is False`; `can_offset`
  simmetrico vero per coppie `redditi_diversi`/`redditi_diversi`; `ruleset_at` prima del primo
  ruleset → `TaxRulesetNotFound`, mai un fallback silenzioso.
- `test_tax_calc.py` — consumo FIFO per anno di formazione; voci scadute escluse dal totale ma
  **presenti** nel dettaglio (`is_expired=true`, mai sparite); perimetri separati (amministrato
  conto A ≠ conto B ≠ dichiarativo aggregato); il nominale non viene mai mutato dal calcolo.
- `test_tax_classification.py` — **trappola ETC**: un asset con `asset_type="etf"` (derivato
  dalla regex `_ETF_HINT_RE` su un nome che in realtà è un ETC) non diventa `etf_armonizzato`
  senza il segnale forte (ISIN + "UCITS" nel nome); override utente vince sempre sul derivato;
  `asset_type="crypto"` → `not_codified` → mai in un totale.
- `test_tax_api.py` — **scenario Trade Republic**: un conto, due periodi, `GET
  /tax/regimes/resolve?on=` restituisce il regime giusto prima e dopo il cambio;
  `effective_from` duplicato → 409; apertura con perimetro incoerente (regime dichiarativo +
  `financial_account_id` valorizzato, o viceversa amministrato senza conto) → 400 esplicito;
  test di riflessione anti-divergenza (ogni campo dei dataclass del ruleset compare nel JSON
  servito, altrimenti la build fallisce); 404 cross-workspace su ogni `{id}`.
- `test_rls_tax.py` — le 4 tabelle nuove, **tutti i 4 comandi** (select/insert/update/delete)
  cross-workspace, non solo select+insert.

**Frontend** — 8 nuovi file vitest (labels con fallback su codice sconosciuto, Settings tab,
pagina regole, periodi di regime col caso Trade Republic, i 4 empty state della vista
zainetto, dialog apertura con assert che il perimetro **non** è preselezionato, card
classificazione asset, label scadenza con `vi.setSystemTime`). Assert trasversale ovunque
compaia un totale: se la copertura è parziale, `TaxCoverageNotice` è nel DOM.

**Regressione** — l'intera suite esistente resta verde; in particolare i 7 call site di
`recompute_position` non sono toccati.

---

## Verifica end-to-end

```bash
cd backend && ruff check . && pytest
```

```bash
cd frontend && npm run lint && npm run test && npm run build
```

Poi su Docker, sul workspace reale:
1. `/settings/tax` → residenza Italia per l'anno corrente, persistita dopo reload.
2. `/settings/tax?tab=rules` → tre versioni di regolamento, aliquote, matrice, assunzioni
   marcate; a 375px la matrice è una lista, non una tabella che scorre.
3. Conto Trade Republic → due periodi consecutivi (dichiarativo fino al cambio IBAN,
   amministrato dopo); `GET /tax/regimes/resolve` restituisce il regime giusto prima e dopo la
   data del cambio.
4. Un asset con classificazione non codificata in portafoglio → escluso dal calcolo,
   segnalato, ogni totale che lo coinvolge marcato parziale.
5. `/investments/tax` da zero → empty state onesto, non uno zero; inserimento di un saldo di
   apertura (es. 1.500 € formati nel 2022) scegliendo esplicitamente il perimetro → card con
   badge "Inserito da te", riga 2022 con scadenza 31/12/2026.

---

## Cosa NON è in FETTA 1

Motore a lotti LIFO, eventi realizzativi, compensazione progressiva evento-per-evento,
override per singolo evento, chiusura d'anno (**FETTA 2**, brief sotto). Vista dichiarativa
avanzata e proiezione "se vendo oggi" / simulatore ordine di vendita (**FETTA 3**, richiede
FETTA 2). Regime gestito (modello predisposto, non implementato). Cripto, derivati,
certificati, ETF non armonizzati: la classe fiscale esiste come dato ma è `not_codified` →
esclusa e segnalata.

---

# FETTA 2 — motore a lotti (brief operativo)

Decisioni prese con l'utente prima di scrivere codice (stessa disciplina di FETTA 1: la
tensione normativa qui sotto era esplicitamente lasciata aperta da FETTA 1, non un dettaglio
tecnico da inventare in corsa).

## Decisione: perimetro del LIFO

**Il LIFO consuma i lotti SEMPRE per singolo conto**, mai aggregato tra conti diversi anche
se stesso perimetro (dichiarativo). Motivazione: un broker ha una custodia fisica separata e
non vede cosa possiedi altrove — per l'amministrato è esattamente come funziona nella realtà
(il sostituto d'imposta preleva/compensa solo su ciò che vede lui). Per il dichiarativo,
l'aggregazione tra conti resta ma avviene **a valle**, sullo zainetto (già aggregato per
perimetro fin da FETTA 1), non nel motore di consumo dei lotti stesso — la tensione con la
risposta AdE 204/2023 (LIFO sulla posizione complessiva del contribuente) è quindi
consapevolmente non risolta al livello del motore, spostata sul fatto che lo zainetto
compensa comunque a valle su tutto il perimetro dichiarativo. Marcata
`FISCAL ASSUMPTION REQUIRING VALIDATION` nel codice.

Questo NON contraddice il vincolo già scritto sopra (chiave `tax_lots` = `(workspace_id,
asset_id)`, non partizionata per conto): il vincolo resta per non chiudere la porta a un
futuro cambio di consumo aggregato, ma FETTA 2 filtra sempre per `financial_account_id` nella
query di consumo.

**Correzione fatta durante l'implementazione** (domanda dell'utente: "perché LIFO, è
specifico dell'Italia?"): il criterio di consumo (LIFO) è una prassi amministrativa
dell'Agenzia delle Entrate, non una regola universale — altri paesi usano criteri diversi
(USA: FIFO di default; UK: share-pooling; non verificato con ricerca fresca in questa
sessione, solo l'esistenza di alternative è certa). Per questo `lot_consumption_order`
("lifo" | "fifo") è un campo di `TaxRuleset` (`app/tax/base.py`), valorizzato `"lifo"` sui 3
ruleset italiani — MAI cablato dentro `tax_lot_calc.py`, che lo riceve come parametro
esplicito. Stessa filosofia già seguita per aliquote/categorie/regimi: una regola
giurisdizione-specifica è sempre un dato dichiarato, mai un comportamento fisso nel motore
generico.

## Decisione: derivato, non persistito (stesso principio di FETTA 1)

**Nessuna tabella `tax_lots` in FETTA 2**: i lotti e gli eventi realizzativi si calcolano a
lettura da `investment_transactions` (unica sorgente di verità, SPEC §35), esattamente come
`position_calc.py` deriva le posizioni — mai un secondo ledger da tenere sincronizzato. Stesso
precedente già citato in FETTA 1 (`compute_historical_series`,
`portfolio_analytics.py:654`): l'utente corregge/retrodata i movimenti, un lotto congelato
diverge silenziosamente. Il vincolo sulla chiave sopra resta comunque valido nel caso in cui
in futuro servisse persisterli per performance.

## Motore puro: `app/services/tax_lot_calc.py`

Parallelo a `position_calc.py` (mai modificato, riusa `Protocol MovementLike` ma **non** la
conflazione `fees + tax` di quel modulo — vedi sopra "Due vincoli non negoziabili"):

- **Costo del lotto (buy/opening)**: `qty * price + fees`. `tax` NON entra nel costo — è un
  esito (ritenuta), mai un onere accessorio.
- **Provento della vendita (sell)**: `qty * price - fees`. Stesso principio: `tax` non riduce
  il provento, il realizzo si calcola al lordo della ritenuta.
- **Consumo LIFO**: stack per `(financial_account_id, asset_id)`; una vendita consuma dal
  lotto più recente indietro nel tempo finché la quantità non è coperta (una vendita può
  attraversare più lotti). Ogni porzione consumata genera un `RealizedTaxEvent` con
  `formation_date` = data della VENDITA (la minus/plusvalenza si forma al realizzo, non
  all'acquisto), `gain_or_loss = proceeds_portion - lot_cost_portion`.
- **Split**: scala quantity/unit_cost di ogni lotto aperto dello stesso asset, stesso
  principio di `position_calc.py` (il valore totale non cambia).
- **`adjustment`**: delta positivo → lotto sintetico con `price` fornito come costo (se
  `price` assente, escluso con warning — nessun costo inventabile); delta negativo → consumo
  LIFO silenzioso, **nessun** `RealizedTaxEvent` (è una correzione dati, non una cessione
  reale — stesso principio di `position_service.py` per gli adjustment).
- **`dividend`**: mai un evento di costo/vendita sul lotto (stesso `_NO_EFFECT_TYPES` di
  `position_calc.py`) — è reddito di capitale, gestito come `event_kind="income"` verso
  `TaxTreatment`, non tocca i lotti.
- Come già oggi in `position_calc.py`: nessuna eccezione su dati "sporchi" (vendita che
  eccede la quantità posseduta) — warning accumulato, risultato onesto, mai un blocco.

## Classificazione e trattamento per evento

Ogni `RealizedTaxEvent` (buy/sell reali, non i lotti sintetici da adjustment) viene
classificato DOPO il calcolo puro, nel service DB-aware (`tax_realized_service.py`):
`jurisdiction.derive_asset_class`/override (`tax_classification_service.py`, riuso diretto)
→ `jurisdiction.treatment(asset_class, "sale", trade_date)` → se `not_codified`, l'evento è
escluso dal totale e segnalato (stessa "copertura parziale" di FETTA 1), mai un numero
inventato.

## Integrazione con lo zainetto

Un `RealizedTaxEvent` con `gain_or_loss < 0` diventa un `LossPocketEntry` con
`source="computed"` (il campo esiste già dal design di FETTA 1,
`app/services/tax_calc.py::LossPocketEntry.source`) — **nessuna modifica a
`build_loss_pocket`**, solo un nuovo produttore di entry accanto alle aperture manuali.
`formed_under_ruleset_code` risolto dal server sulla data di vendita, stesso principio delle
aperture manuali.

## Compensazione progressiva evento-per-evento

Per ogni `RealizedTaxEvent` con `gain_or_loss > 0` (plusvalenza), PRIMA di considerarla
imponibile: cerca capacità disponibile nello zainetto dello stesso perimetro con
`can_offset(loss_category, gain_category, on)` vero, consuma FIFO per anno di formazione
(stessa `CarryForwardRule`, riusa la stessa assunzione già marcata in FETTA 1), riduce la
plusvalenza imponibile e la capacità residua del pozzo di pari importo. Gli eventi si
processano in **ordine cronologico** per perimetro (non per conto): una compensazione decisa
oggi deve rispecchiare l'ordine reale in cui gli eventi sono accaduti nel tempo, mai
ricalcolata "a ritroso" con il senno di poi.

## Cosa resta fuori anche da FETTA 2 (rimandato a dopo)

**Override per singolo evento**: **FATTO** (2026-09-05) — `tax_realized_event_overrides`
(migration 0040), integrato in `tax_realized_service.py`, endpoint dedicati
(`GET /tax/realized-events`, `PUT`/`DELETE .../override`), UI minimale su
`/investments/tax`. Un evento e' identificato dalla coppia
`(lot_transaction_id, sell_transaction_id)`, univoca per costruzione.

**Chiusura d'anno** (`tax_year_closures`): **deliberatamente NON costruita** — chiarito con
l'utente (2026-09-05) che lo zainetto calcolato da Lumio e' uno strumento decisionale
("come muoversi negli investimenti"), non un dato usato per compilare una dichiarazione dei
redditi reale. Ha senso solo per il perimetro **dichiarativo** (nell'amministrato e' la banca,
sostituto d'imposta, a tenere il conteggio ufficiale — l'utente non dichiara nulla di suo).
Il congelamento si puo' introdurre in futuro se e quando servira' davvero (nessuna finta
implementazione preventiva) — la docstring di `tax_calc.py` lo marca gia' come unica
eccezione futura al principio "derivato, non persistito".

**Codifica classi asset mancanti**: **certificati FATTO** (2026-09-05) — trattamento
`sale`, `redditi_diversi` simmetrico come azioni, nessun coefficiente speciale (ricerca
normativa: art. 67 TUIR, stesso regime delle azioni). `codified=True` in
`TAX_ASSET_CLASSES`. **Cripto e ETF non armonizzato rimandati**: cripto ha una timeline di
aliquote indipendente e disconnessa dai confini dei ruleset esistenti (26%+franchigia
2.000€ fino al 2024, 33% senza franchigia dal 2025, 33%/26%-stablecoin dal 2026) e richiede
concetti di schema nuovi (franchigia, versionamento temporale indipendente); ETF non
armonizzato è tassato all'aliquota IRPEF marginale progressiva (23-43%) del contribuente,
incompatibile con il modello `TaxTreatment.rate: Decimal` flat-rate — Lumio non conosce il
reddito personale complessivo, non è un gap "da codificare" ma un'incompatibilità
architetturale.

## Ordine di implementazione

1. **FATTO** — `tax_lot_calc.py` (puro, nessun DB), verificato a mano (LIFO/FIFO
   parametrizzato, separazione fees/tax, split, oversell, adjustment). 2. **FATTO** —
   `tax_realized_service.py` (DB-aware: legge `investment_transactions`, classifica,
   produce `ClassifiedRealizedEvent[]`, esclude e segnala asset non codificati/conti senza
   regime a quella data). 3. **FATTO** — `tax_gains_service.compute_tax_summary` orchestra
   aperture manuali + eventi calcolati in un'unica lettura; `GET /tax/loss-pocket` mostra le
   minusvalenze `computed` accanto a `user_opening` (`tax_calc.build_loss_pocket` non
   modificata, resta sul solo pool di perdite). 4. **FATTO** — `tax_calc.compute_taxable_gains`
   (nuova funzione pura, compensazione progressiva cronologica per perimetro, FIFO sul pool)
   + `GET /tax/taxable-gains`. Verificato end-to-end (smoke reale via API, non solo unit):
   una vendita che genera sia una minusvalenza che una plusvalenza nello stesso giorno
   (stesso esempio motivante dell'utente) compensa correttamente, zainetto "grezzo" mai
   mutato alla fonte. 5. **DA FARE** — Frontend: la vista zainetto (`/investments/tax`) deve
   mostrare le minusvalenze `computed` insieme a quelle manuali (badge diverso, coerente col
   principio "calcolato vs inserito dall'utente" già in FETTA 1) + una vista/sezione per
   `GET /tax/taxable-gains` (imposta dovuta, capienza residua per perimetro).

---

## Assunzioni fiscali da validare (`FISCAL ASSUMPTION REQUIRING VALIDATION`)

Da marcare nel codice e mostrare in UI, mai da trattare come certezza:

1. **Ordine di consumo FIFO per anno di formazione** — fonte debole, prassi bancaria più che
   norma esplicita.
2. **Minusvalenze pregresse dichiarativo → zainetto amministrato** — le fonti si
   **contraddicono** su cosa succeda passando da un regime all'altro. Per questo il saldo di
   apertura chiede il perimetro esplicitamente all'utente, senza dedurlo.
3. **LIFO aggregato vs perimetro per-intermediario** — la risposta AdE 204/2023 dice che il
   LIFO va applicato alla posizione complessiva del contribuente, mentre lo zainetto
   amministrato è per intermediario. Tensione reale, non risolta — rilevante solo per FETTA 2.
4. **Coefficiente 48,08% sui titoli di Stato** — verificato ma non su fonte primaria diretta.
5. **Riporto condizionato alla dichiarazione effettiva (solo regime dichiarativo)** — l'art.
   68 TUIR condiziona il riporto quadriennale al fatto che la minusvalenza sia stata indicata
   nel modello Redditi dell'anno di realizzo: se un anno viene omessa, si perde subito, non ai
   4 anni. Lumio non ha modo di verificare se l'utente l'ha davvero dichiarata — lo assume. Il
   dialog di saldo di apertura per il perimetro dichiarativo deve rendere esplicita questa
   condizione con una nota: è un rischio che non esiste nell'amministrato, dove è la banca a
   tenerne conto.

Nessun numero prodotto da Lumio va usato in dichiarazione senza validazione di un
commercialista, e la UI lo dice sempre (disclaimer permanente, non un modal una tantum).

## Limite noto: una sola giurisdizione per query, non giurisdizione-per-evento (2026-09-05)

Domanda dell'utente: "se ho uno storico fiscale in UK e nel 2026 sono passato in Italia,
`/investments/tax` mi mostra anche la situazione UK?". Oggi `JURISDICTIONS`
([registry.py](backend/app/tax/registry.py)) contiene **solo l'Italia** — lo scenario non è
riproducibile in pratica, nessuna seconda giurisdizione esiste da selezionare in
`WorkspaceTaxResidence`.

Esiste però un gap architetturale reale, da tenere a mente se/quando si aggiungerà una
seconda giurisdizione: `resolve_tax_context` (`tax_context.py:40`) risolve **una singola
giurisdizione** in base alla data della query (`on`, tipicamente oggi), e quella stessa
istanza viene passata per intero a `list_realized_events`/`compute_tax_lots` — non c'è
risoluzione **per evento** in base alla data in cui l'evento è effettivamente accaduto. Un
utente con residenza UK fino al 2025 e Italia dal 2026 vedrebbe, con l'architettura attuale,
anche gli eventi del 2023 (epoca UK) valutati con le regole della giurisdizione VIGENTE OGGI
(Italia), non con quelle che erano davvero in vigore allora. Nessun codice da scrivere ora
(non c'è una seconda giurisdizione con cui verificarlo) — solo tracciabilità per non
dimenticarlo quando servirà davvero.

---

# FETTA 3 — brief di design (2026-09-05, nessun codice ancora)

Riprende i due punti lasciati aperti in "Cosa NON è in FETTA 1": vista dichiarativa avanzata
e proiezione "se vendo oggi" / simulatore ordine di vendita. Richiede FETTA 2 (motore a
lotti, zainetto computed, compensazione progressiva), ora completa.

## Scope A — Vista dichiarativa avanzata

Riepilogo annuale, per perimetro e categoria di reddito (redditi_diversi/redditi_capitale),
pronto da passare a un commercialista: plusvalenze lorde, minusvalenze usate per anno di
formazione, imponibile netto, imposta stimata — un "quadro RT-like" a sola lettura, mai un
modulo compilabile o un dato da inviare all'Agenzia.

Riuso pressoché totale: `tax_realized_service.list_realized_events` +
`tax_calc.compute_taxable_gains` già producono tutti i numeri; manca solo il
raggruppamento per anno solare e la vista/tabella dedicata. Nessuna nuova entità DB, nessun
nuovo calcolo — è essenzialmente un aggregatore + presentazione sopra dati che esistono già.

**DECISION REQUIRED**: basta una vista a schermo (`/investments/tax`, nuova sezione "Riepilogo
annuale") o serve anche un export (CSV/PDF) da poter allegare a una mail al commercialista?
La vista a schermo è a costo minimo (riuso totale); l'export aggiunge una libreria di
generazione file e un job — sproporzionato se l'utente copia i numeri a mano oggi.

## Scope B — Simulatore "se vendo oggi"

Per un asset in portafoglio, l'utente indica una quantità ipotetica; il sistema calcola,
senza persistere nulla, il gain/loss risultante iniettando un movimento sintetico
`sell(quantity=X, price=prezzo_corrente, trade_date=oggi)` nella stessa lista di movimenti
reali passata a `compute_tax_lots` — il motore consuma i lotti esistenti secondo il
`lot_consumption_order` della giurisdizione esattamente come farebbe con una vendita vera.
Il risultato si passa poi a `compute_taxable_gains` (aggiungendolo agli eventi reali) per
mostrare l'effetto marginale: quanto di questa ipotetica plusvalenza verrebbe compensato dal
pool residuo, quanto resterebbe imponibile, quanta imposta stimata ne deriverebbe.

Nessuna scrittura DB, nessun nuovo modello — puro riuso delle funzioni esistenti con un
movimento sintetico invece che uno letto da `investment_transactions`. Rischio principale:
tenere ben separato "eventi reali" da "eventi simulati" in ogni punto della UI, per non
confondere mai un numero ipotetico con uno realizzato (stesso principio del disclaimer
sempre visibile).

**DECISION REQUIRED**: la simulazione riguarda un asset alla volta (l'utente apre l'asset,
inserisce una quantità) o multi-asset ("se vendessi tutto quello in plusvalenza")? Consiglio:
partire da singolo asset — è il caso d'uso più chiaro e riusa la pagina asset esistente
([AssetDetailPage.tsx](frontend/src/features/portfolio/AssetDetailPage.tsx)) senza una nuova
superficie UI.

## Scope C — "Simulatore ordine di vendita": non è quello che sembra

Nota architetturale prima di preventivare questo scope: se la giurisdizione impone un
`lot_consumption_order` fisso (LIFO in Italia), l'utente **non può scegliere quale lotto
vendere** — lo decide sempre il motore in base all'ordine dichiarato dalla giurisdizione.
"Simulatore ordine di vendita" come concetto libero (scegliere il lotto più conveniente da
liquidare) non è legalmente disponibile in Italia: sarebbe un numero che Lumio mostra ma che
non corrisponde a un'operazione fiscalmente valida.

Quello che resta possibile è già lo Scope B: simulare "se vendo N unità oggi" e vedere quale
lotto verrebbe consumato (per via del LIFO) e con quale risultato — non una scelta, solo una
proiezione di ciò che accadrebbe comunque.

**Raccomandazione**: non costruire uno Scope C separato — collassa in Scope B, che già
risponde alla domanda reale ("cosa succede se vendo?") senza promettere una libertà di scelta
che la norma non consente.

## Priorità consigliata

1. Scope B (simulatore "se vendo oggi", singolo asset) — riuso quasi totale, nessuna nuova
   entità, risponde alla domanda operativa più concreta ("conviene vendere questo ora?").
2. Scope A (vista dichiarativa annuale, solo schermo) — riuso totale, utile ma meno urgente
   di una decisione d'investimento imminente.
3. Export CSV/PDF per lo Scope A — solo se l'utente lo richiede esplicitamente dopo aver
   usato la vista a schermo; costo non giustificato a priori.

---

# Regime gestito — brief di design (2026-09-05, nessun codice ancora)

Il modello dati lo prevede già (`TaxRegimeOption.calc_model: "realized" | "accrued"`,
[base.py:152](backend/app/tax/base.py:152)) ma nessun motore lo calcola. Questo brief
descrive cosa servirebbe, non lo implementa.

## Perché non è un'estensione di FETTA 2, ma un secondo motore parallelo

Il regime gestito tassa il risultato **maturato** a fine anno (plusvalore/minusvalore
dell'intero patrimonio nel wrapper), non i singoli realizzi. Tre conseguenze architetturali:

1. **Il motore a lotti (LIFO/FIFO, FETTA 2) non si applica**: non esistono "eventi di
   realizzo" da classificare, perché non conta quando/a che prezzo hai comprato un singolo
   lotto — conta solo il valore del patrimonio a inizio e fine anno. `tax_lot_calc.py` e
   `tax_realized_service.py` restano specifici del `calc_model="realized"`.
2. **Serve una valutazione puntuale del patrimonio a due date** (1 gennaio e 31 dicembre,
   o data di apertura/chiusura contratto se infrannuale) — non un evento transazionale.
   Lumio ha già l'infrastruttura di valutazione (prezzi storici, sostanza analitica —
   [lumio_sostanza_analitica](docs/SPEC.md) §30) ma quella calcola andamento nel tempo per
   dashboard, mai un "valore fiscale a una data" pensato per un calcolo d'imposta.
3. **I redditi di capitale sono compensabili al suo interno** — l'opposto
   dell'amministrato/dichiarativo, dove `redditi_capitale` non compensa mai (vedi
   `_OFFSET_RULES` in [italy.py:63](backend/app/tax/rulesets/italy.py:63), unico per l'intera
   giurisdizione). Questo significa che **la matrice di compensazione oggi non è
   regime-aware, solo ruleset-aware**: per il gestito servirebbe una seconda matrice
   `OffsetRule` selezionata in base al regime attivo sul conto, non solo alla data. Cambio
   architetturale non banale: `can_offset` andrebbe parametrizzato per `calc_model`, non solo
   per `TaxRuleset`.

## Cosa servirebbe (alto livello, non un piano di implementazione)

- Un secondo servizio (`tax_accrued_calc.py` o simile) che, per un conto in regime gestito,
  legge il valore di patrimonio a inizio/fine periodo (riuso dei prezzi storici esistenti,
  nuova funzione di valutazione "a una data" se non già isolabile da quella esistente) e
  produce un singolo `AccruedTaxEvent` per anno/periodo, non una lista di eventi per
  transazione.
- Una matrice di compensazione alternativa (redditi_capitale ↔ redditi_diversi compensabili)
  attiva solo quando il calc_model del regime è `accrued`.
- Il perimetro dello zainetto per il gestito è il singolo contratto (mai aggregato, nemmeno
  con altri conti gestiti dello stesso workspace) — coerente con `pocket_scope="per_account"`
  già usato dall'amministrato, ma da confermare che sia davvero lo stesso significato per un
  wrapper gestito (un "contratto" gestito potrebbe non coincidere 1:1 con un
  `financial_account` in Lumio).

## DECISION REQUIRED (da confermare con l'utente, non da inventare)

1. **Serve davvero ora?** Nessun conto reale dell'utente è oggi in regime gestito
   (verificare: se non lo è, il ROI di questo lavoro è zero fino a quando non lo sarà).
   Consiglio: non avviare l'implementazione finché non c'è un caso d'uso reale — il modello
   dati è già pronto a non renderlo impossibile, che era l'unico impegno preso in FETTA 1.
2. **Cadenza della valutazione**: sempre anno solare (1/1–31/12) o segue le date di
   apertura/chiusura del contratto/periodo di regime (come già avviene per `TaxRegimePeriod`)?
   Rilevante se un conto passa da amministrato a gestito a metà anno.
3. **Fonte del valore di patrimonio a una data**: riusare la stessa pipeline di
   `asset_prices`/sostanza analitica, o serve una snapshot dedicata più robusta (es. l'ultimo
   prezzo noto potrebbe non coincidere con l'estratto conto ufficiale del gestore, che è la
   fonte legale del valore maturato)? Tensione reale: Lumio calcola sui prezzi di mercato che
   conosce, il gestore potrebbe avere un NAV proprio.

Raccomandazione complessiva: **non implementare finché non emerge un caso d'uso reale**
(decisione 1) — a differenza di FETTA 3, qui il costo di un secondo motore parallelo è alto
e il ritorno è zero senza un conto gestito reale da calcolare.
