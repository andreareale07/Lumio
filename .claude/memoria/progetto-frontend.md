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
- `AreaTrendChart` ha `yAxisDomain="tight"` per i prezzi (il default parte da 0).

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
