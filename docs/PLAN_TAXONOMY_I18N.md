# Piano: tassonomia categorie language-agnostic (i18n)

Stato: **PIANO, non implementato.** Nessun codice toccato da questo
documento. Scritto in risposta alla DECISION REQUIRED "testo backend"
(vedi memoria di sessione `lumio_frontend_redesign_phase1.md`): l'utente
ha scelto la strada (a) — il backend restituisce chiavi i18n, il frontend
traduce — e ha chiesto un piano scritto prima di toccare migration/schema,
dato che qui la portata è molto più ampia del caso già risolto
(`job_registry.py`, vedi commit `3545f62`).

## Perché è un problema diverso da job_registry.py

Il job registry era un dataclass Python puro, nessuno storage, nessun
consumer se non l'endpoint `/jobs`. La tassonomia è tutt'altro:

- **`name` è una colonna reale** in `categories` (PostgreSQL), non un
  campo Python — 149 righe seminate dalla migration
  `0022_category_taxonomy_reseed.py` da
  `app/classification/taxonomy.py:TAXONOMY`.
- **Lo stesso campo `name` è condiviso da categorie di sistema E utente.**
  Le categorie che l'utente crea da sé (`CreateCategoryDialog.tsx`,
  `is_system=false`) hanno un `name` che è testo libero scelto
  dall'utente — non può mai diventare una chiave i18n, e non deve: è
  "suo", nella lingua che ha scelto lui, comunque cambi la lingua della UI.
- **`name` alimenta anche il prompt AI**, non solo la UI:
  `app/ai/prompt.py` costruisce il prompt di classificazione leggendo
  `option.name`/`option.parent_name`/`option.hint` direttamente dalla
  tabella `categories` — la stessa riga che la UI mostra all'utente.
  Sdoppiare "nome per la UI" da "nome per il prompt" è un secondo
  problema dentro il problema, vedi sezione dedicata sotto.
- Tocca anche l'export Google Sheets (`app/integrations/google/
  report_builder.py`, non ancora ispezionato in dettaglio) e qualunque
  report che stampi il nome categoria.

## Buona notizia: la chiave i18n esiste già

`TaxonomyCategory.code` (es. `"casa.affitto"`, `"trasporti.carburante"`)
è **già** uno slug stabile, univoco, mai riusato (vedi il commento
in cima a `taxonomy.py` sulle 14 UUID storiche + le altre congelate).
Non serve una nuova colonna né una migration per aggiungere l'identità
della chiave — serve solo un namespace i18n frontend `categories`
strutturato per `code`, e un modo per la UI di sapere **quando** usarlo
invece del `name` letterale.

## Come distinguere sistema vs utente

`is_system: bool` esiste già sul modello `Category` ed è già esposto in
API e frontend (`CategoriesSettingsPage.tsx` lo usa per il badge
"Sistema" e per nascondere azioni di modifica/eliminazione). Diventa
anche il discriminante per la traduzione:

- `is_system === true` → il frontend ignora `category.name` per la UI e
  traduce `categories:<code con "." sostituito da un separatore
  i18next-safe>` (es. `t("categories:casa.affitto")` — i18next supporta
  `.` come separatore di nesting nelle chiavi, quindi la UI userebbe
  `t(category.code)` diretto se il JSON è annidato per componenti di
  `code` — DA VERIFICARE in pratica se serve invece appiattire con un
  separatore diverso, es. `_`, per evitare collisioni con chiavi che sono
  sia foglia sia genitore, es. `casa` radice e `casa.affitto` figlio
  nello stesso namespace).
- `is_system === false` → il frontend mostra `category.name` cosà com'è,
  MAI tradotto — è testo dell'utente.

Il backend non cambia il campo `name` in DB (resta la fonte di verità
per l'AI e per compatibilità), ma **aggiunge** un modo per il frontend di
risalire al `code` quando serve la chiave — che già c'è: `Category.code`
è già nella risposta di `GET /categories` (verificare, non confermato in
questo giro — assunto probabile dato che il frontend già lo confronta in
`CategoriesSettingsPage.tsx:47`).

## Il problema del prompt AI (separato, ma correlato)

Il prompt di classificazione (`app/ai/prompt.py`) userebbe `name` per
costruire l'elenco di categorie che l'LLM vede. Se in futuro l'utente
seleziona "en" come lingua UI, NON significa che il prompt debba diventare
inglese: le transazioni bancarie che arrivano dai parser sono quasi
sempre in italiano (nomi merchant, causali) — un prompt in inglese con
`description_raw` in italiano è probabilmente **peggiore**, non
neutro. Raccomandazione: il prompt resta sempre in italiano
indipendentemente dalla lingua UI dell'utente, quindi legge sempre
`Category.name` (il valore di sistema, che è sempre italiano) e MAI una
traduzione. Questo va deciso esplicitamente con l'utente quando si arriva
a implementare — non è nello scope di "tradurre la UI", è una scelta di
prodotto sulla qualità della classificazione.

## Passi di implementazione (quando si deciderà di procedere)

1. **Verificare il contratto attuale** di `GET /categories` /
   `CategoryOut` — confermare che `code` è già esposto (probabile ma non
   verificato in questo giro).
2. **Costruire `locales/{it,en}/categories.json`** dalle 149 righe di
   `TAXONOMY` (script una tantum, non a mano) — struttura a scegliere fra
   piatta (`{"casa.affitto": "Affitto"}`) o annidata
   (`{"casa": {"affitto": "Affitto"}}`); la piatta evita l'ambiguità
   radice/figlio menzionata sopra ed è più facile da generare/validare
   con uno script che itera `TAXONOMY`.
3. **Hook frontend** tipo `useCategoryLabel()` (stesso pattern di
   `useTransactionTypeLabel()` già introdotto in `002f880`): riceve una
   `Category`, ritorna `category.is_system ? t(`categories:${category.code}`) : category.name`.
   Sostituire gli usi diretti di `category.name`/`c.name` in
   `CategoriesSettingsPage.tsx`, `CategoryFormDialog.tsx`,
   `CreateCategoryDialog.tsx`, `features/categories/utils.ts`
   (`buildCategoryOptions`/`categoryLabel`, che già costruiscono le
   opzioni raggruppate per padre — il punto di aggancio naturale).
4. **NON toccare** `app/ai/prompt.py`, `app/db/seed_data.py`, la
   migration `0022`, né la colonna `name` in DB — restano l'origine dati
   sia per l'AI sia per il seed, invariati.
5. **Test**: uno script/test che verifica ogni `code` in `TAXONOMY` ha
   una chiave corrispondente in ENTRAMBI `locales/it/categories.json` e
   `locales/en/categories.json` (stesso spirito del test
   anti-falso-positivo già esistente su `catalog.py` che itera l'intero
   catalogo) — altrimenti una categoria nuova aggiunta a `taxonomy.py` in
   futuro rischia di comparire come chiave grezza in UI senza che nessun
   test lo scopra.
6. **Export Google Sheets**: verificare se `report_builder.py` deve
   anch'esso tradurre (probabilmente sà, se l'export riflette la lingua
   scelta dall'utente) — DECISION REQUIRED separata quando si arriva a
   questo punto, perché l'export è generato server-side senza un
   "linguaggio UI" naturale da leggere (a differenza della UI, dove
   `i18n.language` è sempre disponibile) — serve decidere se passare la
   lingua come parametro della richiesta di export.

## Cosa NON è incluso in questo piano

- Non copre `app/classification/catalog.py` (i pattern merchant→categoria,
  es. `SystemPattern`): quel modulo non contiene testo mostrato
  all'utente, solo `category_code` — nessuna traduzione necessaria lì.
- Non copre eventuali altri messaggi backend in italiano al di fuori di
  job registry e tassonomia (non censiti in questo giro — la sessione si
  è fermata dopo aver trovato questi due moduli come i più rilevanti per
  la UI Settings/Categorie).

## Stima approssimativa

Passi 1–3 (contratto + JSON + hook + sostituzione call site): una fetta
di lavoro paragonabile a quella già fatta per `job_registry.py`, forse
leggermente più ampia per il numero di call site frontend coinvolti (4
file). Passo 5 (test anti-regressione sulle chiavi) è piccolo ma
necessario. Passo 6 (export) è un secondo giro separato con la sua
DECISION REQUIRED — non stimato qui.
