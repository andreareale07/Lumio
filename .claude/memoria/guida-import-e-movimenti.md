# Guida: import, parser e movimenti

Spec: `docs/SPEC.md`, `docs/SPEC_DEDUP_TRANSACTION.md`.

## Flusso di import (3 passi)
1. `POST /imports` (upload): il conto **non** e' obbligatorio (`financial_account_id`
   nullable, migration 0038). Restituisce una preview con i conti candidati.
2. `POST /imports/{id}/resolve-account`: l'utente conferma un candidato, ne sceglie un
   altro o crea un conto al volo. Nessun match si applica da solo, neanche con IBAN
   esatto.
3. `POST /imports/{id}/confirm` avvia `import_job.py`.
- Il matching dei candidati (`account_matching.py`) usa l'IBAN attuale, poi lo storico
  IBAN, **mai il nominativo** (conti cointestati, nomi diversi): il nominativo serve solo
  a precompilare la creazione di un conto.
- Frontend: `ImportWizard.tsx` (upload -> account -> confirm).

## Parser
- `BankParser` (`app/parsers/base.py`); oggi c'e' solo Trade Republic (PDF). Il CSV passa da
  profili di mapping (`ImportMapping`, `csv_import.py`).
- Capability opzionali (restituiscono `None` se non supportate): `extract_transfer_counterparty`,
  `extract_account_info`, `default_transaction_type`.
- Il parser TR legge le colonne **dall'intestazione**, non da soglie fisse (fix `b7faae7`).
- **Regola per ogni parser futuro**: si mappa solo cio' che l'etichetta afferma
  ("Interessi" -> `interest`), mai cio' che si deduce da uno strumento di pagamento
  ("Bonifico" non e' `transfer`: il default va sul segno, credit -> income e
  debit -> expense). L'etichetta grezza si conserva in `source_type_raw`.
- Stub: `TradeRepublicParser.extract_account_info` restituisce sempre `None`, perche' il
  formato dell'intestazione con l'IBAN del titolare non e' mai stato verificato su un PDF
  reale (l'unico IBAN noto e' quello della filiale).

## Trasferimenti interni (non sono mai spesa ne' entrata)
- `transfer_recognition.py`: per TR la controparte e' nel testo ("Outgoing/Incoming
  transfer for {nome} ({iban})"). Si confronta prima l'IBAN, con tutti i conti del
  workspace, IBAN storici compresi (`financial_account_iban_history`); poi il nominativo
  dei **membri del workspace**. Se l'IBAN non e' noto si ricade sul nome. Classificazione
  automatica, sempre correggibile.
- Lo storico IBAN si popola automaticamente quando cambia l'IBAN di un conto, oppure a
  mano (`/accounts/{id}/iban-history`). Rimuovere una voce non annulla le transazioni gia'
  rimappate.

## Mappatura dei tipi (`/settings/transaction-types`)
- `transaction_type_mappings` per workspace + parser + etichetta grezza; qui `transfer` e'
  un target valido (e' una scelta dell'utente).
- Rimappatura retroattiva: si applica solo se il tipo attuale e' uguale al default del
  parser; se e' diverso lo si considera una correzione manuale e si salta (le correzioni
  manuali vincono sempre).

## Deduplicazione
- `transaction_dedup.py`: fingerprint SHA-256 (conto + data + importo quantizzato + valuta +
  descrizione normalizzata + tipo), **mai unique**: si confrontano le occorrenze
  (min(esistenti, nuove) = duplicati). I casi ambigui finiscono in REVIEW
  (`transaction_review_items`); le decisioni dell'utente sono persistite
  (`transaction_dedup_decisions`). Lo stato dell'import `ready_for_review` resta finche'
  ci sono review aperte.
- `transaction_persistence.py` e' la pipeline unica di persistenza, condivisa da job e
  decisione di review: non duplicarla.
