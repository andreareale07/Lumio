# Progetto: frontend (React + TypeScript + Vite)

Percorso: `frontend/`. React 18, react-router 7, TanStack Query, react-hook-form + zod,
Tailwind 4, Recharts, i18next, icone lucide-react. Build servita da nginx nel container
`frontend`, che fa da proxy per `/api/`.

## Struttura
- `src/features/<dominio>/`: pagine e hook (`api.ts` con hook react-query) per dominio.
  Esempio di percorso non ovvio: le categorie stanno in `features/categories/`, non in
  `features/settings/categories/`.
- `src/components/ui/`: design system condiviso (Dialog, Drawer, Pagination, JobRunStatus,
  Tabs, Combobox...). `components/layout/`: AppShell, Topbar, `PageToolbarContext.tsx`,
  `pageWidths.ts`. `components/charts/ChartCard.tsx`.
- `src/lib/`: utilita' pure (`usePagedList`, `period`, `format`, `stats`, `modifiedDietz`,
  `apiClient`, `errorMessage`).
- `src/app/i18n.ts`, `src/locales/{it,en}/<namespace>.json` (15 namespace).
- Il nome prodotto arriva da `VITE_APP_NAME` (build arg), mai hardcoded.

## Meccanismi da riusare (non reinventare)
- **Dialog/Drawer montano via `createPortal(..., document.body)`**: un `<form>` annidato in
  un altro `<form>` fa partire un submit GET nativo silenzioso. Ogni nuovo overlay
  (modal, popover, dropdown) deve usare un portal da subito.
- **Azioni primarie di pagina -> `usePageToolbar(node)`** (portal nel Topbar, `hidden md:flex`)
  + duplicato `md:hidden` sotto l'h1 per il mobile. E' un portal e non uno stato condiviso
  perche' uno stato in AppShell causerebbe un loop di render. Il pulsante dell'empty
  state resta separato.
- Larghezza: `PAGE_WIDTH_WIDE` per le pagine con molti dati, `max-w-*` per le pagine-form.
  Con griglie a 2 colonne passare a 1 colonna se c'e' un solo gruppo.
- Liste lunghe: `components/ui/Pagination.tsx` + `lib/usePagedList.ts` (paginazione lato
  client: le API di regole/import/asset non sono paginate). Pattern completo:
  `features/rules/RulesPage.tsx`; con filtri in URL: `TransactionsPage.tsx`.
- Stato job: `components/ui/JobRunStatus.tsx` + `features/activity/ActivityIndicator.tsx`.
- `ChartCard` rende sempre anche una `<table className="sr-only">`: ogni testo del grafico
  compare 2 volte nel DOM (nei test usare `findAllByText`/`.first()`).
- `lib/trimSeries.ts::trimLeadingEmpty` taglia i punti iniziali vuoti di una serie (usato in
  Spese/Entrate, Dashboard, Patrimonio, dettaglio conto, rendimento Investimenti). Il filtro
  merchant (`merchant` / `no_merchant`) esiste su cash-flow, by-category e `/transactions`;
  `MerchantList.tsx` riconosce la riga "Senza merchant" dal testo italiano del backend.
- `FloatingPanel` ricalcola la posizione ogni volta che cambia l'identita' di `anchorRef`: passare
  sempre un ref STABILE (mai un oggetto creato nel render), altrimenti ciclo di render infinito.
- `AreaTrendChart` ha `yAxisDomain="tight"` per i prezzi (il default parte da 0).

- **Periodo (dal 2026-11-06):** `components/filters/PeriodNavigator.tsx` + `lib/usePeriodNavigator.ts`.
  Una sola copia nel corpo della pagina (non piu' nel Topbar ne' duplicata `md:hidden`): pulsanti di testo
  Mese/Anno/3M/12M(/Tutto con `allowAll`), icona calendario che apre `PeriodPanel` (trimestre, date
  digitabili gg/mm/aaaa, `RangeCalendar` a 1 mese su mobile / 2 su desktop), sotto ‹ etichetta › e il
  periodo con le date esatte. Modi nell'URL: `granular` (+`granularity`/`anchor`), `custom` (+`from`/`to`),
  `all`, `rolling` (+`rolling=3m|12m`, calcolato da oggi con `resolveRolling`). Giorno/settimana/semestre
  non sono piu' offerti in UI ma l'URL li accetta. Opzione `family` (es. `PERIOD_FAMILY` = "analysis":
  Panoramica, Spese/Entrate, Patrimonio): senza stato nell'URL si ripristina l'ultimo periodo della famiglia
  da `sessionStorage` (scritto nell'URL con replace); un link con periodo esplicito vince sempre.
- **Mobile: `components/ui/BottomSheet.tsx`** (portal, chiusura visibile + Escape + sfondo) e
  `FloatingPanel` che ora resta dentro lo schermo (margine 8px, `shiftX`). Da riusare per i filtri.
- **Intervallo dei grafici (1G…Max):** `RangeSelector` e' solo testo (no bordi/sfondi, attivo sottolineato,
  area di tocco 40px) e va messo in alto accanto al valore; stato nell'URL con `lib/useRangeParam.ts`
  (`?range=3M`, ricorda l'ultimo scelto per famiglia in sessionStorage; famiglia "investments").
  `AreaTrendChart` e' esplorabile con `onActivePointChange(index|null)` (puntatore su un wrapper
  `touch-pan-y`, non gli eventi di Recharts): l'intestazione mostra valore/variazione/data del punto; senza
  la prop resta il tooltip classico. `lib/useIsDesktop.ts` = breakpoint `md` per scegliere popover o
  `BottomSheet` (es. `ActivityIndicator`).
- **Filtri liste:** `components/filters/FilterBar.tsx` (tipi `SelectFilter`/`StaticFilterChip`/`QuickFilter`/
  `RemoteOptions`; opzioni remote via `useRemoteOptions(query)` chiamato da un componente dedicato) +
  `lib/useUrlListFilters.ts`; `features/transactions/TransactionFilterBar.tsx` ne e' un wrapper sottile
  (merchant remoti, riepilogo). Stringhe condivise in `common:filters.*`. Nei test `tests/matchMedia.ts`
  (`setDesktop`) sceglie popover (desktop) o bottom sheet (default mobile).
- **Controlli su smartphone:** `Button` (sm/md/icon), `Input`, `Select`, `Tabs`, `BackLink`, Topbar sono
  44px sotto `md`; `global.css` forza 16px su input/select/textarea (iOS zooma sotto) e `touch-action:
  manipulation`. Per i link testuali dentro le card usare `inline-flex min-h-11 items-center md:min-h-0`.
- **Bottom bar mobile** (`components/layout/MobileNav.tsx`): una sola griglia `grid-cols-[repeat(5,1fr)]`
  per barra + voci espanse ("Altro" -> "Chiudi", niente Drawer). Va usato `1fr` e NON
  `grid-cols-5` (= `minmax(0,1fr)`): cosi' le colonne prendono la larghezza dell'etichetta piu'
  lunga e il testo non si tronca mai. Se sfora su schermi stretti, ridurre il font (ora 11px).

- **App mobile (2026-11-07):** `lib/platform.ts::isNativeApp()`; `lib/apiClient.ts` usa `getApiBase()` (server scelto nel
  guscio) e, nel nativo, token nel Keystore con refresh single-flight; `lib/privacy.ts` nasconde gli importi (remount di
  `AppRouter` come la lingua); `SwipeableRow`, `usePullToRefresh`, `lib/haptics.ts`. Dettagli in `task-app-mobile.md`.

## Regole i18n
- Nuovo namespace: aggiungerlo **sia** a `resources` **sia** all'array `ns` in `app/i18n.ts`
  (se ne manca uno, `t()` restituisce la chiave grezza senza errori).
- Enum del backend -> namespace `enums` tramite hook per feature (es.
  `useTransactionTypeLabel`), mai un `Record` di stringhe italiane.
- Etichette condivise -> `common`; contenuto delle pagine Impostazioni ->
  `settings:items.<key>.page.*`.
- Plurali con `_one`/`_other` + `{{count}}`; enfasi interna con `<Trans components=...>`.
- Debito noto: `features/categories/utils.ts` (`categoryLabel`, `CATEGORY_KIND_LABELS`) ha
  ancora stringhe italiane hardcoded.

## Altre insidie
- `friendlyErrorMessage`: un 401 al login significa "credenziali errate", altrove
  "sessione scaduta". Sceglie il messaggio il chiamante, non l'helper.
- jsdom non ha `window.matchMedia`: il polyfill e' in `tests/setup.ts` (serve per i grafici).
- Workspace nuovo: snapshot di patrimonio/portfolio non ancora calcolati -> gestire
  sempre il caso "nessun dato" (bug reale trovato in Dashboard).

## Comandi (da `frontend/`)
`npm run lint` · `npx tsc -b` · `npm run test` (vitest) · `npm run build` ·
`npm run test:e2e` (Playwright: vedi le insidie in `guida-metodo-sviluppo-e-test.md`).
