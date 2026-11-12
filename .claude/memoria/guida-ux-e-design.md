# Guida: UX e design di prodotto

Regole date dall'utente (l'app e' pensata per uso quotidiano, da parte di una persona con
molti dati reali: una pagina che funziona con 5 voci e si rompe con 300 e' un difetto
di prodotto).

## Liste
- Ogni elenco che cresce con l'uso: ricerca + filtro per stato + conteggio ("N regole, M
  attive") + paginazione "da-a di totale" + layout largo, righe compatte in un unico
  elenco (non una card per riga). La sola paginazione non basta.
- Se una feature produce un record per evento/riga (non un aggregato), valutare subito una
  **pagina dedicata** paginata invece di una sezione inline: va fatto prima che l'utente se
  ne accorga.
- Mattoni da usare: vedi `progetto-frontend.md` (Pagination, usePagedList, RulesPage).

## Drill-down e range dei grafici (richiesta utente, 2026-11-06)
- Modello di riferimento: "Dove vanno i soldi" (`CategoryHierarchyList`): righe cliccabili
  (`clickableRowClasses`) che aprono il `DrillDownDrawer` (andamento + ripartizione +
  transazioni + "Vedi tutte"), espansione per i livelli figli. Ogni elenco di aggregati
  (merchant, conti, asset...) deve comportarsi cosi', non essere una lista statica.
- Mai mostrare range in cui non c'e' ancora nessun dato: un tratto a zero prima del primo
  movimento schiaccia la curva. Le serie temporali passano da `lib/trimSeries.ts`
  (`trimLeadingEmpty`); la finestra si scarica intera se serve a confronti (YoY), si taglia
  solo la visualizzazione e il subtitle del grafico riflette il range mostrato.

## Filtri di una lista (modello: `TransactionFilterBar`, Movimenti)
- Ricerca testuale in cima (debounce 300ms, nell'URL come `q`, lato server); sotto, una sola riga:
  filtri rapidi ("Da verificare"), un chip per ogni filtro attivo (clic = cambia valore con
  ricerca nell'elenco, X = toglie), "+ Filtro" per i filtri non ancora attivi, "Azzera filtri"
  (riporta anche il periodo al default). Sotto, riepilogo "N movimenti · entrate · uscite" da
  `GET /transactions/summary` (stessi filtri della lista, `list_filters` condiviso nel backend).
- Un filtro impostato da un link esterno (merchant, import) e' un chip rimovibile; la lista
  vuota con filtri attivi dice "Nessun risultato" + azzera. Il periodo resta nel navigatore
  del Topbar (come in ogni pagina). "Senza categoria" non e' un filtro rapido: e' gia' incluso
  in "Da verificare" (`_is_pending_review`).
- Selezione multipla (OR) per conto/categoria/tipo/merchant: valori ripetuti nell'URL
  (`?category=a&category=b`, `buildQueryString` accetta array) e liste nel backend
  (`list_filters`). Liste lunghe: ricerca nel picker (appare oltre 6 voci); i merchant sono
  remoti (`GET /transactions/merchants?q=`: piu' frequenti con conteggi + "N su totale").
- Non fatto: "piu' usate" e raggruppamento per le categorie (solo ricerca), importo, viste salvate.
- **Componente condiviso (2026-11-06):** `components/filters/FilterBar.tsx` per OGNI lista (Movimenti, Regole,
  Import, Tipi transazione, Eventi realizzati, Utile realizzato): ricerca opzionale, filtri rapidi, chip,
  "+ Filtro", "Azzera filtri", riepilogo. Mobile: pannelli = `BottomSheet` con "Azzera"/"Applica · N" (la
  scelta si applica solo all'Applica, bozza locale), niente autofocus nel picker, righe da 44px, chip bassi
  ma con area di tocco ~44px; desktop: popover con applicazione immediata. `single: true` per filtri a
  valore singolo (si applica e chiude al tocco). Stato nell'URL con `lib/useUrlListFilters` (`q` + parametri
  ripetuti, `replace` per la ricerca); Tipi transazione (piu' tabelle per pagina) resta con stato locale.

## Selettore di periodo (decisione 2026-11-06, dopo mockup a confronto)
- Scelte comuni sempre a vista come testo (Mese, Anno, 3M, 12M, Tutto), nessun bordo; calendario in un
  pannello (bottom sheet su mobile, popover su desktop) con scorciatoie per trimestre, date digitabili e
  calendario. "Anno" e' gia' "da inizio anno": niente scorciatoia doppia. Frecce solo dove ha senso
  (mese/anno/trimestre); periodo attivo sempre scritto in chiaro con le date.
- Periodo ricordato solo dentro una famiglia di pagine con contesto comune (Analisi; Investimenti da fare),
  non tra pagine senza nesso (Movimenti e dettaglio conto restano a se').
- Preset di grafici di prezzo/portfolio (da fare): solo testo, senza bordi, attivo scuro e sottolineato, in
  alto accanto al valore (stile Trade Republic); set completo 1G 1S 1M 3M 6M 1A 5A Max.
- Bersagli di tocco 44px su mobile (area invisibile ammessa), calendario con inizio/fine non solo a colore.

## Regole e condizioni (decisione 2026-11-12, dopo mockup a confronto)
- Una regola si mostra sempre come **frase** ("Se la descrizione contiene «X» e l'importo e' tra A e B, assegna C"), mai come "campo / operatore /
  valore". Prima di salvare si vede l'impatto: quanti movimenti cambiano / sono gia' giusti / sono protetti da una correzione manuale, con elenco e
  parte evidenziata. L'avviso "regola troppo ampia" scatta per i movimenti che verrebbero tolti da ALTRE categorie; l'avviso di conflitto conta anche i movimenti
  protetti di un'altra categoria e propone di escludere la parola che li distingue ("non contiene").
- Si parte dal movimento (parole a pulsanti; le parole con cifre non si scelgono: cambiano a ogni movimento) o da una proposta; l'espressione
  regolare resta un operatore avanzato. Un suggerimento e' una scelta tra proposte (piu' precisa / consigliata / piu' ampia), non un testo da accettare.

## Azioni
- Le azioni primarie di una pagina vanno **sempre nella toolbar** (`usePageToolbar`):
  icona lucide + testo breve, mai un link accanto all'h1 o in fondo al contenuto. Le azioni
  di una sezione interna restano inline (es. `IbanHistorySection`).
- Azioni con impatto (es. "Applica alle transazioni esistenti"): pulsante in cima che apre
  una finestra con l'**anteprima dell'impatto**.

## Processi lunghi
- Lo stato arriva dal server (`job_runs`), non da un flag locale: deve sopravvivere al
  ricaricamento e dire **dove seguirlo** (link "Segui in Attivita'", indicatore globale nel
  Topbar, avanzamento x/N ed ETA quando disponibili). Mai un "In corso" generico.

## Contenuti e numeri
- Prima il riepilogo, poi il dettaglio. Lo stato si esprime con la forma (badge, colore),
  non solo a parole.
- Mai un numero fuorviante: meglio nascondere un KPI che mostrare "0,00 EUR" quando manca
  l'attivita'. Le approssimazioni si dichiarano (Modified Dietz non va mai chiamato "TWR").
- Metriche analitiche sulle pagine dedicate (Spese/Entrate/Investimenti), non nella
  Dashboard.
- Mai un dato indovinato: un match automatico (IBAN, conto) si propone e l'utente lo
  conferma.

## Configurazioni
- "Provare/confrontare/tornare a" una configurazione = lista di **profili nominati** con
  attivazione esplicita, non un record unico (segnale nella richiesta: parole come
  "provare", "confrontare", "tornare").
- Le funzioni da utente esperto (integrazioni) restano nascoste nell'esperienza base.

## Mobile first (priorita' dichiarata dall'utente, 2026-11-06)
- "Deve funzionare anche e soprattutto da smartphone." Ogni nuovo controllo (filtri, periodo,
  selettori, pannelli) si progetta e si verifica a ~375px prima che su desktop: tocco >= 44px,
  nessuna dipendenza dall'hover, pannelli che restano nello schermo (valutare bottom sheet),
  attenzione alla tastiera virtuale. Verificare col browser integrato (`resize_window`
  preset mobile), non solo ragionando sul layout.

- Checklist di rifinitura (2026-11-06): nessuno scroll orizzontale a 375px; bersagli >= 44px (anche con area
  invisibile); input a 16px; ogni popover ancorato a un pulsante vicino al bordo diventa bottom sheet o
  `FloatingPanel` (clampato nello schermo); azioni di pagina: la principale a tutta larghezza, le altre in
  griglia 2x2 con etichette che vanno a capo. Audit rapido: script JS nel browser che conta gli elementi
  interattivi <40px e gli elementi oltre `innerWidth` per ogni rotta.

## Metodo
- Per scelte di layout importanti l'utente ha apprezzato un mockup a confronto prima
  dell'implementazione (Dashboard, Vista B).
- Per ogni redesign di UI ricorrente (filtri, selettori, navigazione) l'utente vuole: ricerca
  online delle best practice con fonti, mockup interattivi a confronto (2-3 alternative),
  scelte motivate, e solo dopo l'implementazione (funzionato per i filtri di Movimenti).
- Se l'utente chiede di essere interrogato con domande di chiarimento, va fatto fino a
  esaurirle, prima di proporre.

## Residui noti (al 2026-10-24, verificare)
Pagine con job lunghi che mostrano ancora solo un "In corso" generico: NetWorth, Dati di
mercato, Valute. Restyle del menu Impostazioni (lista lunga) richiesto ma non pianificato.
