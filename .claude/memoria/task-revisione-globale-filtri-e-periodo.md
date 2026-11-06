# Task: revisione globale di filtri, selettori di vista e range temporale

Richiesta dell'utente del 2026-11-06, da svolgere come attivita' a se' (non ancora iniziata).
Obiettivo: portare in TUTTA l'app lo stesso lavoro minuzioso fatto per i filtri di Movimenti,
con priorita' **smartphone**.

## Requisiti (detti dall'utente)
1. **Mobile first, davvero.** "E' importante che tutto funzioni anche e soprattutto da
   smartphone." Ogni controllo va progettato e verificato prima a ~375px (tocco, niente hover,
   pannelli che non escono dallo schermo, tastiera virtuale), poi desktop.
2. **Ambito globale:** tutti i filtri e tutti i selettori di "vista", in particolare la gestione
   del **range temporale** (oggi diversa da pagina a pagina).
3. **Metodo obbligato** (lo stesso usato per Movimenti, apprezzato):
   ricerca online delle best practice (citare le fonti) -> **mockup interattivi a confronto**
   (con alternative, non una sola) -> scelte consapevoli e motivate -> implementazione
   -> verifica su browser anche in viewport mobile.
4. Coerenza: lo stesso schema ovunque (un solo "linguaggio" di filtri), non soluzioni locali.

## Punto di partenza: cosa esiste (verificare nel codice, puo' essere cambiato)
- **Modello di riferimento gia' fatto:** `features/transactions/TransactionFilterBar.tsx`
  (ricerca `q`, filtro rapido, chip con selezione multipla, "+ Filtro", "Azzera filtri" che
  resetta anche il periodo, riepilogo da `GET /transactions/summary`, merchant remoti da
  `GET /transactions/merchants`). Regole nella sezione "Filtri di una lista" di
  `guida-ux-e-design.md`. **Verificato solo su viewport desktop**: la resa mobile (chip che
  vanno a capo, pannelli `FloatingPanel` da 288px, tastiera) NON e' stata provata.
- **Periodo:** `components/filters/PeriodNavigator.tsx` + `lib/usePeriodNavigator.ts` (stato
  nell'URL: `mode`/`granularity`/`anchor`/`from`/`to`; `allowAll` solo in Movimenti, dove il
  default e' "tutto"). Montato nel Topbar con `usePageToolbar` (`hidden md:flex`) e duplicato
  `md:hidden` sotto l'h1 per il mobile. Granularita' diverse per pagina: Dashboard, Spese,
  Entrate, Patrimonio e Movimenti tutte e 6 (day..year); dettaglio conto solo
  mese/trimestre/anno.
- **Secondo sistema temporale, diverso:** `components/charts/RangeSelector.tsx` (preset
  1G/1S/1M/3M/6M/1A/5A/Max, stato locale, non nell'URL) in `AssetDetailPage` e
  `PortfolioSummaryBlock`. Due modelli (navigatore periodo vs preset) per la stessa idea.
- **Filtri locali ad hoc, non nell'URL:** `RulesPage` (ricerca + stato), `ImportsPage`
  (stato), `TransactionTypeMappingsPage`, `TaxRealizedEventsPage`, `RealizedPositionsPage`,
  schede Investimenti/portfolio. Da censire con un giro completo prima di progettare.
- Drill-down e link tra pagine passano il periodo/filtri via URL (es. drawer merchant ->
  `/transactions?merchant=..&mode=custom&from=..&to=..`): ogni nuovo schema deve restare
  compatibile con questi link.
- Componenti utili: `FloatingPanel` (portal, richiede `anchorRef` STABILE), `Combobox`,
  `Drawer`, `Dialog`, `Pagination`/`usePagedList`; `lib/trimSeries.ts` per i range dei grafici.

## Decisioni prese (2026-11-06, dopo censimento, ricerca e mockup interattivi)
- **Filtri delle liste:** resta lo stile di Movimenti (ricerca + chip + "+ Filtro" + "Azzera filtri" +
  riepilogo), gia' deciso in precedenza; si estende a tutte le liste. Da fare solo l'adattamento mobile:
  bottom sheet con "Applica" al posto dei popover da 288px, bersagli di tocco 44px, niente `autoFocus`
  nel picker su mobile, pagine con un solo filtro con la stessa barra ridotta.
- **Periodo (pagine con navigatore):** "tipo 2". Pulsanti sempre a vista (testo: Mese, Anno, 3M, 12M,
  Tutto) + icona calendario; sotto ‹ etichetta › attive solo per mese/anno/trimestre. "Anno" = anno in
  corso (coincide con "Da inizio anno": niente scorciatoia a parte). Il pannello del calendario contiene
  "T4 2026 · trimestre" e "Trimestre scorso" (scorrevole con le frecce), campi Dal/Al digitabili
  (gg/mm/aaaa, errori inline), calendario a 1 mese su mobile (bottom sheet) e 2 su desktop (popover).
  Inizio/fine intervallo marcati anche con grassetto + sottolineatura, non solo colore. Periodo attivo
  sempre scritto in chiaro con le date esatte sopra la lista. Via giorno/settimana/semestre dall'interfaccia.
- **Portfolio e grafici di prezzo (stile Trade Republic):** preset COMPLETI (1G 1S 1M 3M 6M 1A 5A Max) come
  solo testo, senza bordi ne' sfondi, inattivo grigio chiaro e attivo scuro con sottolineatura, posizionati
  in alto accanto al valore (non sotto il grafico, non in bottoni grandi); area di tocco invisibile alta
  ~40px. Valore grande + variazione dell'intervallo scelto; trascinando sul grafico valore, data e
  variazione si aggiornano fino a quel punto. Sostituisce `RangeSelector` (bottoni attuali).
- Dettagli di Trade Republic non verificati online (solo preset 1G/1S/1M/1J/Max e variazione legata
  all'intervallo confermati da un forum): il resto e' interpretazione, da correggere con l'utente.

- **Persistenza:** solo dentro una famiglia di pagine (Analisi: Panoramica, Spese, Entrate, Patrimonio;
  Investimenti quando si fara' la fetta portfolio); Movimenti e dettaglio conto a se'.

## Stato implementazione (2026-11-06)
- FETTA 1 (periodo) FATTA, non committata: `PeriodNavigator` riscritto, `usePeriodNavigator` con `rolling`,
  `selectGranularity`/`selectBucket` e `family`; `period.ts` con `resolveRolling`, `parseDisplayDate`,
  `PERIOD_FAMILY`; nuovi `BottomSheet`, `RangeCalendar`; `FloatingPanel` clampato nello schermo; pagine
  Dashboard/Spese-Entrate/Patrimonio/Dettaglio conto/Movimenti aggiornate; vitest 232 verdi, lint/tsc/build ok;
  verifica manuale a 375px e 1280px su account sintetico (mobile: sheet, 2 tocchi, 3M, persistenza Panoramica;
  desktop: popover, trimestre).
- Spec E2E `dashboard-golden-path.spec.ts` aggiornata al nuovo selettore ma NON rieseguita.
- FETTA 2 (portfolio) FATTA, non committata: `RangeSelector` discreto in alto, `useRangeParam` (URL +
  famiglia "investments"), `AreaTrendChart` esplorabile (portfolio mostra rendimento% e data del punto;
  titolo mostra prezzo/variazione/data), vitest 245 verdi. Verificato a 375px con dati sintetici (hover
  col mouse: il drag col dito NON provato su un telefono vero, ne' lo scroll verticale sopra il grafico).
- Rifinitura mobile fatta: popup Attivita' (bottom sheet su mobile), bersagli 44px (Button/Input/Select/
  Tabs/Topbar/BackLink/link nelle card Conti), input a 16px, azioni di Investimenti in griglia. Pagine
  controllate con audit: Panoramica, Conti, Movimenti, Import, Impostazioni (nessun overflow orizzontale).
- FETTA 3 (filtri) FATTA, non committata: `FilterBar` condivisa + `useUrlListFilters`; Movimenti, Regole,
  Import (stato nell'URL), Tipi transazione (stato locale), Eventi realizzati e Utile realizzato (asset/
  conto a valore singolo) migrati; vitest 252 verdi (test vecchi dei selettori di stato aggiornati).
  Verificato a 375px (sheet "Aggiungi filtro", merchant remoti con conteggi, 2 scelte + Applica, chip,
  azzera) e a 1280px (popover immediato) su Movimenti; Regole/Import/Fiscale NON provati nel browser
  (account senza dati), solo con test.
- Residui: tastiera virtuale reale, drag col dito, E2E Playwright, controllo in inglese, audit mobile delle
  pagine Investimenti/Fiscale/Regole/Attivita' con dati. (Vecchio elenco "Da fare" sotto, superato:) fetta 3 = filtri (adattamento mobile della barra di Movimenti, estesa a Regole/Import/Tipi/
  Fiscale/Utile realizzato con chip, URL, bottom sheet). Verificare anche la resa in inglese.

## Domande ancora aperte
- Nessuna al momento.

## Domande aperte iniziali (superate dalle decisioni sopra, tenute per memoria)
- Selettore di periodo su mobile: barra nel Topbar, riga sotto l'h1, bottom sheet, preset
  rapidi (Questo mese / 3M / Anno / Max / Personalizzato)? Un solo modello (periodo +
  preset) per tutta l'app, o due?
- Granularita' e navigazione prev/next: servono tutte e 6 ovunque? Cosa vuol dire
  "granularita'" per chi guarda un grafico vs una lista?
- Filtri su mobile: pannello a tutto schermo/bottom sheet con "Applica" (stato draft separato
  dall'applicato) o applicazione immediata? Dove vivono i chip (scroll orizzontale vs a capo)?
- Persistenza: ricordare l'ultimo periodo/filtri tra pagine? Viste salvate?
- Quali pagine hanno bisogno di filtri veri e quali solo di ricerca.
- Accessibilita': tocco >= 44px, focus, aria, tastiera virtuale che copre i pannelli.

## Piano di lavoro suggerito
1. Censimento (Explore): ogni controllo di filtro/periodo/vista per pagina, con screenshot
   a 375px e 1280px dello stato attuale.
2. Ricerca online (best practice: filtri e date range su mobile, bottom sheet, preset di
   periodo, finanza personale) con fonti.
3. Mockup interattivi a confronto (almeno 2-3 alternative per periodo e per filtri mobile),
   proposta motivata, attesa di scelta dell'utente.
4. Implementazione a fette piccole (prima il periodo, poi i filtri pagina per pagina),
   componenti condivisi in `components/filters/`, URL come fonte di verita'.
5. Verifica per fetta in viewport mobile (`resize_window` preset mobile) e desktop; test
   vitest per i componenti condivisi; aggiornare `guida-ux-e-design.md`.

## Regole di progetto da ricordare
- Commit solo su richiesta, mai `Co-Authored-By` (vedi CLAUDE.md).
- Nuovi overlay sempre via portal; pytest solo su Postgres/Redis effimeri.
- Prove nel browser con account di test sintetici (`*-verify@example.com`), mai sui dati
  reali dell'utente; lo stack Docker va ricostruito dopo ogni modifica.
- A fine attivita' aggiornare questa scheda (cosa e' stato deciso e perche').

## Prompt di avvio
Il prompt pronto per iniziare e' stato consegnato all'utente in chat il 2026-11-06; il
contenuto operativo e' tutto in questa scheda.
