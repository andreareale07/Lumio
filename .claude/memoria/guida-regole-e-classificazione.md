# Guida: regole di categorizzazione, suggerimenti, applicazione (rifatte il 2026-11-12, migration 0048)

Motivo del rifacimento: una regola aveva una sola condizione, il form mostrava "campo / operatore / valore" senza spiegare nulla e i
suggerimenti raggruppavano per testo identico (inutili con riferimenti variabili). Mockup scelti: B (parole del movimento), D (proposte per
precisione), C (piu' condizioni E/O). Prototipo: artifact privato "Regole Lumio prototipo".

## Modello e motore
- `rules.conditions` (JSONB, 1..10) + `rules.match_mode` (`all` = E, `any` = O) sostituiscono `field/operator/value` (0048: backfill sotto
  `NO FORCE RLS`, downgrade con perdita dichiarata: tiene la prima condizione di testo). Nessuna tabella figlia: una regola si legge e scrive per intero.
- Operatore `not_contains` (2026-11-12, nessuna migration: le condizioni sono JSONB): "non contiene", vero anche con merchant assente; serve a escludere
  una parola da una frase condivisa (es. "CANONE CONTO" e "CASHBACK ... CANONE CONTO"). Solo per le regole utente, il catalogo di sistema non lo usa.
- Condizioni: testo (`description`/`merchant` + 6 operatori, come prima) oppure `{"field":"amount","operator":"between","min","max"}` (stringhe
  decimali, almeno un estremo) sul **valore assoluto** dell'importo. `app/services/rules_engine.py`: `Condition`, `rule_matches`, `evaluate`;
  `matches()` resta invariato perche' lo usa anche il catalogo di sistema. `Probe`/`ClassifiableRow` hanno `amount` opzionale (senza, l'importo non scatta).
- API: `RuleCreate/Update` accettano anche la forma abbreviata `field/operator/value` (una condizione); `RuleOut` espone solo `conditions`.
- **Regex**: `check_regex_safety` (max 200 caratteri, niente quantificatori annidati) nello schema; la regex gira in Python dentro la richiesta
  di anteprima, `re` non ha timeout.

## Anteprima (`POST /rules/preview`, nessuna scrittura)
`rule_preview_calc.py` (puro) + `rule_preview_service.py` (DB). Per una regola NON salvata divide i movimenti che combaciano in `change` (cambierebbero),
`ok` (gia' nella categoria) e `protected` (correzione manuale `user`/`manual` in un'altra categoria: le correzioni manuali vincono sempre). Restituisce
anche `recategorized` (dei `change`, quelli che hanno gia' un'altra categoria: l'avviso "regola troppo ampia" usa solo questi, i senza-categoria sono
l'effetto voluto) e gli intervalli `spans` da evidenziare, calcolati col motore (la regex non e' riproducibile in JS). `other_category` + `conflict_samples` (2026-11-12): TUTTI i movimenti che combaciano con un'altra categoria, protetti inclusi (prima l'avviso li ignorava e
la regola sbagliata "non faceva nulla" perche' i movimenti erano scelte manuali); il costruttore propone "Escludi «X»" con la prima parola del movimento
in conflitto assente da quello di partenza (`exclusionWord`). Tetto 50.000 movimenti recenti
(`truncated`). Non considera la priorita' tra regole: se una regola piu' prioritaria vince, il numero reale puo' essere minore.

## Suggerimenti (`GET /rules/suggestions`)
`rule_suggestion_calc.py` (puro, euristica deterministica senza AI): dei movimenti che l'utente ha corretto a mano nella stessa categoria cerca le
**frasi stabili** (parole senza cifre, mai iniziate/finite da un connettivo italiano) comuni alla meta' o piu' e ne misura l'impatto su tutto il workspace.
Opzioni: `recommended` (copre le correzioni cambiando meno categorie altrui, a parita' 2+ parole e la piu' corta), `precise` (consigliata + una frase
indipendente), `broad` (frase piu' ampia). `ambiguous` = la frase ampia e' condivisa anche da un'altra categoria scelta dall'utente.
**Causa dello screenshot originale**: il job di riclassificazione assegna il merchant `Bonifico Sepa Istantaneo Trn` a tutti i bonifici; il vecchio codice
raggruppava per merchant e proponeva la stessa regola per categorie diverse. Ora un merchant condiviso con altre categorie (cambierebbe piu' movimenti
di quanti sono gia' giusti) non produce regole per merchant e passa all'analisi delle frasi.

## Applicazione ai movimenti esistenti
`POST /classification/reclassify` accetta `rule_id`: il job (`reclassification_job`, arg arq in coda) agisce solo sui movimenti che combaciano con
quella regola (`load_rule_matching_ids`), pipeline completa, mai le correzioni manuali. Con un'altra riclassificazione in corso risponde 409 (non
restituisce il job in corso: farebbe credere che la regola sia stata applicata).

## Insidie
- **Mai lanciare pytest con l'env del DB usato per la verifica nel browser**: la fixture `_clean_tables` fa TRUNCATE anche per i test puri (costa ~2 s/test).
- Le anteprime/suggerimenti non vanno provati su dati reali dell'utente (solo account di test).
- Un job `reclassify` assegna i merchant ai movimenti ("N merchant aggiornati"): cambia i suggerimenti disponibili.
