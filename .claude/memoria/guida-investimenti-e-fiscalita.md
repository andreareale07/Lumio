# Guida: investimenti, prezzi e fiscalita'

Spec: `docs/SPEC_STOCK_PRICE.md`, `docs/SPEC_TAX_REGIME.md` (FETTA 1 + FETTA 2).

## Posizioni
- `investment_transactions` e' l'**unica fonte di verita'**; `positions` e' sempre derivata
  (`position_service.recompute_position`, costo medio ponderato in `position_calc.py`).
  Carico iniziale = movimento `opening`; una modifica manuale della posizione diventa un
  movimento `adjustment`. Mai un secondo modello da riconciliare.
- Le posizioni si legano all'`account_id`, mai all'`account_type`: i conti reali sono ibridi
  (TR, Fineco). Tutti i conti tranne le carte di credito contano come liquidita'.
- L'ordine dei movimenti nello stesso giorno conta (`movement_order.py`, fix `65cbbd0`).
- Operazioni societarie (raggruppamento con cambio ISIN, derivati scaduti):
  `corporate_action_*`. Dopo un'unione di asset o una chiusura a zero si ricostruiscono gli
  snapshot.
- Ricalcolo massivo: job `positions_recompute` (Impostazioni > Manutenzione) o
  `scripts/recompute_positions.py`.

## Prezzi di mercato
- `asset_prices` = chiusura giornaliera canonica (non la scrive mai la sola apertura di una
  pagina). `asset_price_quotes` = osservazioni intraday. Quotazione live = cache Redis
  `market:quote:{ws}:{asset}` con lock anti-stampede; se il provider non risponde si
  restituisce l'ultimo dato con `stale=True`, mai un errore.
- Il refresh automatico del portfolio riusa lo stesso job del pulsante "Aggiorna ora" e
  aggiorna solo gli asset con posizione aperta.
- Cache intraday "sufficiente" = numero minimo di punti **e** intervallo coperto minimo
  (`_INTRADAY_MIN_SPAN_HOURS`): contare solo i punti non basta.
- Gap accettato (rimandato dall'utente il 2026-08-17): `asset_prices` e' duplicata per
  workspace invece di essere globale per strumento come `fx_rates`. Da rivedere quando
  arriveranno i workspace con piu' utenti.

## Rendimento
- Modified Dietz (`frontend/src/lib/modifiedDietz.ts`): approssimazione dichiarata, mai
  chiamata TWR. Non conta i dividendi (gap in `position_calc.py`).
- Nessuna media o confronto sul valore assoluto del patrimonio (decisione dell'utente).

## Fiscalita' (Italia, interfaccia `TaxJurisdiction`)
- Regolamento versionato come **dato in codice** (`app/tax/rulesets/italy.py`), mai nel DB.
  Residenza fiscale e regime per conto sono append-only per anno di decorrenza.
- Lo zainetto e' derivato in lettura, mai persistito. Le aperture manuali sono l'unico input
  salvato.
- Motore a lotti (`tax_lot_calc.py`, puro): ordine LIFO/FIFO preso da
  `TaxRuleset.lot_consumption_order`, mai cablato. Si consuma **per singolo conto**, mai in
  aggregato tra conti (decisione dell'utente); l'aggregazione del dichiarativo avviene a
  valle, sullo zainetto.
- **Causalita'**: una minusvalenza compensa solo plusvalenze successive
  (`formation_date <= trade_date`). Bug reale trovato dall'utente sui propri dati.
- La capienza mostrata e' quella **residua** (`remaining_by_perimeter`); i totali grezzi
  restano invariati per audit.
- Le plusvalenze da ETF armonizzati (reddito di capitale) non sono mai compensabili con
  minusvalenze.
- `AssetDetailPage`: la tabella acquisti separa la parte chiusa (rendimento realizzato al
  prezzo di vendita) dalla parte aperta (prezzo attuale) tramite
  `GET /assets/{id}/lot-breakdown`. Prima tutte le righe usavano il prezzo attuale.
- Lumio non da' consulenza: i calcoli servono a orientarsi.
