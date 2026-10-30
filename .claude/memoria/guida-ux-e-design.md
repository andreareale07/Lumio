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

## Metodo
- Per scelte di layout importanti l'utente ha apprezzato un mockup a confronto prima
  dell'implementazione (Dashboard, Vista B).
- Se l'utente chiede di essere interrogato con domande di chiarimento, va fatto fino a
  esaurirle, prima di proporre.

## Residui noti (al 2026-10-24, verificare)
Pagine con job lunghi che mostrano ancora solo un "In corso" generico: NetWorth, Dati di
mercato, Valute. Restyle del menu Impostazioni (lista lunga) richiesto ma non pianificato.
