import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import { buildQueryString } from "../../lib/queryString";
import { useMarketDataProfiles, useMarketDataRefreshStatus, useTriggerMarketDataRefresh } from "../settings/market-data/api";
import type {
  Asset,
  AssetProfile,
  AssetTaxPreview,
  AssetType,
  AssetValuation,
  HistoryPreset,
  InvestmentTransaction,
  InvestmentTransactionType,
  JobRun,
  LotBreakdownRow,
  Portfolio,
  PortfolioAccountLink,
  PortfolioAllocation,
  PortfolioPerformance,
  PortfolioPositions,
  PortfolioSummaryList,
  PortfolioValuation,
  Position,
  PriceHistory,
  SnapshotBackfillTriggered,
  SnapshotRebuildTriggered,
} from "../../types/api";

/** Ambito di uno dei 3 scope possibili per gli analytics del portfolio
 * (redesign Investimenti): tutti i conti (nessun campo), un Portfolio
 * nominato, o "conti non assegnati a nessun Portfolio" — mutuamente
 * esclusivi, stesso principio del backend (`resolve_account_ids`). */
export interface PortfolioScope {
  portfolioId?: string | null;
  unassigned?: boolean;
}

function scopeParams(scope: PortfolioScope): URLSearchParams {
  const params = new URLSearchParams();
  if (scope.unassigned) {
    params.set("unassigned", "true");
  } else if (scope.portfolioId) {
    params.set("portfolio_id", scope.portfolioId);
  }
  return params;
}

function scopeKeyPart(scope: PortfolioScope): string {
  if (scope.unassigned) return "unassigned";
  return scope.portfolioId ?? "all";
}

// --- Assets --------------------------------------------------------------

export const assetsKey = ["portfolio", "assets"] as const;

export function useAssets() {
  return useQuery({ queryKey: assetsKey, queryFn: () => api.get<Asset[]>("/assets") });
}

export interface AssetInput {
  symbol?: string | null;
  isin?: string | null;
  name: string;
  asset_type: AssetType;
  currency: string;
  notes?: string | null;
}

export function useCreateAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AssetInput) => api.post<Asset>("/assets", input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: assetsKey }),
  });
}

export function useUpdateAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: AssetInput & { id: string }) => api.patch<Asset>(`/assets/${id}`, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: assetsKey }),
  });
}

export function useDeleteAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/assets/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: assetsKey }),
  });
}

/** Storico prezzi per il grafico di dettaglio asset (Step 1). I preset
 * giornalieri (1M/3M/6M/1A) vengono persistiti lato backend in
 * `asset_prices` alla stessa chiamata — nessun endpoint separato per
 * "salva" vs "leggi". `refetchIntervalMs` (opzionale, docs/
 * SPEC_STOCK_PRICE.md): per il preset "1G" il backend ora serve/arricchisce
 * `asset_price_quotes` (osservazioni intraday) ad ogni chiamata — ripetere
 * la query a intervalli mostra quei punti via via che si accumulano, senza
 * bisogno di un buffer lato client. `false`/omesso = nessun polling (invariato). */
export function usePriceHistory(assetId: string | null, preset: HistoryPreset, refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: ["portfolio", "assets", assetId ?? "", "price-history", preset] as const,
    queryFn: () => api.get<PriceHistory>(`/assets/${assetId}/price-history?preset=${preset}`),
    enabled: !!assetId,
    refetchInterval: refetchIntervalMs ?? false,
  });
}

/** Rendimento per asset, sempre convertito nella valuta richiesta (default:
 * base_currency del workspace) anche quando prezzo e posizione sono in
 * valute diverse — a differenza del calcolo client-side precedente, che
 * mostrava "—" in quel caso. `currency` esplicito permette di chiedere il
 * prezzo convertito in una valuta diversa da quella base (es. la valuta
 * dell'asset, per confrontare il prezzo attuale con quello di un acquisto
 * storico registrato in quella stessa valuta). `refetchIntervalMs`
 * (opzionale, docs/SPEC_STOCK_PRICE.md): cadenza di polling per il dettaglio
 * asset (`detail_refresh_interval_seconds` del profilo attivo) — il backend
 * serve una live-quote da cache Redis con lock anti-stampede, mai un
 * effetto sul prezzo daily canonico. `false`/omesso = nessun polling
 * (invariato per chiunque non lo passi). */
export function useAssetValuation(assetId: string | null, currency?: string, refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: ["portfolio", "assets", assetId ?? "", "valuation", currency ?? "default"] as const,
    queryFn: () => {
      const query = currency ? `?currency=${encodeURIComponent(currency)}` : "";
      return api.get<AssetValuation>(`/assets/${assetId}/valuation${query}`);
    },
    enabled: !!assetId,
    refetchInterval: refetchIntervalMs ?? false,
  });
}

/** Scomposizione aperto/chiuso per il dettaglio asset — riusa il motore a
 * lotti fiscale (bug reale: il rendimento contro il prezzo attuale non ha
 * senso per una posizione gia' venduta). */
export function useLotBreakdown(assetId: string | null) {
  return useQuery({
    queryKey: ["portfolio", "assets", assetId ?? "", "lot-breakdown"] as const,
    queryFn: () => api.get<LotBreakdownRow[]>(`/assets/${assetId}/lot-breakdown`),
    enabled: !!assetId,
  });
}

/** Colonna "Tasse" della tabella movimenti (seguito di FETTA 2): riusa
 * l'imposta reale per le porzioni gia' vendute, simula "se vendessi oggi"
 * (cumulativo, ordine di consumo fiscale) per i lotti ancora aperti.
 * `currentPrice` nella valuta dell'asset — senza prezzo (posizione non
 * valorizzabile) il backend calcola solo `realized`. */
export function useAssetTaxPreview(assetId: string | null, currentPrice: number | null) {
  return useQuery({
    queryKey: ["portfolio", "assets", assetId ?? "", "tax-preview", currentPrice] as const,
    queryFn: () =>
      api.get<AssetTaxPreview>(
        `/assets/${assetId}/tax-preview${buildQueryString({ current_price: currentPrice ?? undefined })}`,
      ),
    enabled: !!assetId,
  });
}

/** Arricchimento best-effort (Step 3) — sempre 200 con campi `null` quando
 * non disponibile, mai un errore da gestire qui. */
export function useAssetProfile(assetId: string | null) {
  return useQuery({
    queryKey: ["portfolio", "assets", assetId ?? "", "profile"] as const,
    queryFn: () => api.get<AssetProfile>(`/assets/${assetId}/profile`),
    enabled: !!assetId,
  });
}

// --- Portfolios (aggregazione su piu' conti, SPEC §36) --------------------

export const portfoliosKey = ["portfolio", "portfolios"] as const;

export function usePortfolios() {
  return useQuery({ queryKey: portfoliosKey, queryFn: () => api.get<Portfolio[]>("/portfolios") });
}

/** Un singolo Portfolio per id (nome/descrizione per l'header del
 * dettaglio, redesign Investimenti) — non filtra dalla lista gia' in
 * cache: e' una pagina diversa (`/investments/portfolios/:id`), nessuna
 * garanzia che la lista sia gia' stata scaricata in questa sessione. */
export function usePortfolio(portfolioId: string | null) {
  return useQuery({
    queryKey: [...portfoliosKey, portfolioId],
    queryFn: () => api.get<Portfolio>(`/portfolios/${portfolioId}`),
    enabled: !!portfolioId,
  });
}

export interface PortfolioInput {
  name: string;
  description?: string | null;
  currency: string;
}

export function useCreatePortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PortfolioInput) => api.post<Portfolio>("/portfolios", input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: portfoliosKey }),
  });
}

export function useUpdatePortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: PortfolioInput & { id: string }) =>
      api.patch<Portfolio>(`/portfolios/${id}`, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: portfoliosKey }),
  });
}

export function useDeletePortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/portfolios/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: portfoliosKey }),
  });
}

export function portfolioAccountsKey(portfolioId: string) {
  return ["portfolio", "portfolios", portfolioId, "accounts"] as const;
}

export function usePortfolioAccounts(portfolioId: string | null) {
  return useQuery({
    queryKey: portfolioAccountsKey(portfolioId ?? ""),
    queryFn: () => api.get<PortfolioAccountLink[]>(`/portfolios/${portfolioId}/accounts`),
    enabled: !!portfolioId,
  });
}

export function useAddPortfolioAccount(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (financialAccountId: string) =>
      api.post<PortfolioAccountLink>(`/portfolios/${portfolioId}/accounts`, {
        financial_account_id: financialAccountId,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: portfolioAccountsKey(portfolioId) }),
  });
}

export function useRemovePortfolioAccount(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (financialAccountId: string) =>
      api.delete<void>(`/portfolios/${portfolioId}/accounts/${financialAccountId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: portfolioAccountsKey(portfolioId) }),
  });
}

// --- Investment transactions (libro mastro, SPEC §35) ----------------------

export const investmentTransactionsKey = ["portfolio", "investment-transactions"] as const;

export interface InvestmentTransactionFilters {
  financial_account_id?: string;
  portfolio_id?: string;
  unassigned?: boolean;
  asset_id?: string;
  type?: InvestmentTransactionType;
  /** Il backend li accetta gia' (`GET /investment-transactions`) — esposti
   * qui per i flussi Modified Dietz scoped all'anno (`PortfolioSummaryBlock.tsx`). */
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export function useInvestmentTransactions(filters: InvestmentTransactionFilters = {}) {
  const params = scopeParams({ portfolioId: filters.portfolio_id, unassigned: filters.unassigned });
  if (filters.financial_account_id) params.set("financial_account_id", filters.financial_account_id);
  if (filters.asset_id) params.set("asset_id", filters.asset_id);
  if (filters.type) params.set("type", filters.type);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  params.set("limit", String(filters.limit ?? 50));
  params.set("offset", String(filters.offset ?? 0));

  return useQuery({
    queryKey: [...investmentTransactionsKey, filters],
    queryFn: () => api.get<InvestmentTransaction[]>(`/investment-transactions?${params.toString()}`),
  });
}

export interface InvestmentTransactionInput {
  financial_account_id: string;
  asset_id?: string | null;
  trade_date: string;
  type: InvestmentTransactionType;
  quantity?: string | null;
  price?: string | null;
  amount: string;
  fees?: string;
  tax?: string;
  currency: string;
  notes?: string | null;
}

// Le posizioni derivano SEMPRE dai movimenti (mai un'API dedicata per
// "aggiorna la posizione"): invalidare anche `positionsKey` dopo ogni
// create/update/delete e' quindi necessario, non opzionale.
function invalidatePortfolioData(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: investmentTransactionsKey });
  queryClient.invalidateQueries({ queryKey: positionsKey });
  // Anche gli analytics (valore/rendimento aggregati e per riga) devono
  // aggiornarsi dopo un movimento — senza questo, la Panoramica/tabella
  // Posizioni resterebbe stantia finche' non si smonta/rimonta la pagina.
  queryClient.invalidateQueries({ queryKey: ["portfolio", "analytics"] });
}

export function useCreateInvestmentTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: InvestmentTransactionInput) =>
      api.post<InvestmentTransaction>("/investment-transactions", input),
    onSuccess: () => invalidatePortfolioData(queryClient),
  });
}

export function useDeleteInvestmentTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/investment-transactions/${id}`),
    onSuccess: () => invalidatePortfolioData(queryClient),
  });
}

// --- Positions (sempre derivate, mai un UPDATE diretto — SPEC §34) --------

export const positionsKey = ["portfolio", "positions"] as const;

export interface PositionFilters {
  financial_account_id?: string;
  asset_id?: string;
  only_open?: boolean;
}

export function usePositions(filters: PositionFilters = {}) {
  const params = new URLSearchParams();
  if (filters.financial_account_id) params.set("financial_account_id", filters.financial_account_id);
  if (filters.asset_id) params.set("asset_id", filters.asset_id);
  if (filters.only_open !== undefined) params.set("only_open", String(filters.only_open));

  return useQuery({
    queryKey: [...positionsKey, filters],
    queryFn: () => api.get<Position[]>(`/positions?${params.toString()}`),
  });
}

export interface PositionManualEditInput {
  financial_account_id: string;
  asset_id: string;
  quantity: string;
  average_cost: string;
  notes?: string | null;
}

/** Traduce l'input in un movimento `adjustment` lato backend — mai un
 * UPDATE diretto sulla posizione (vedi `position_service.py`). */
export function useEditPositionManually() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ financial_account_id, asset_id, ...input }: PositionManualEditInput) =>
      api.put<Position>(`/positions/by-account/${financial_account_id}/asset/${asset_id}`, input),
    onSuccess: () => invalidatePortfolioData(queryClient),
  });
}

// --- Analytics (SPEC §37): valore, allocation, performance -----------------
// Nessuna conversione valutaria (stesso principio degli analytics M08): i
// valori sono sempre nella valuta prevalente del workspace, risolta lato
// backend quando non specificata.

export function portfolioValuationKey(portfolioId: string | null, unassigned = false) {
  return ["portfolio", "analytics", "valuation", scopeKeyPart({ portfolioId, unassigned })] as const;
}

export function usePortfolioValuation(portfolioId: string | null, unassigned = false) {
  const params = scopeParams({ portfolioId, unassigned });
  return useQuery({
    queryKey: portfolioValuationKey(portfolioId, unassigned),
    queryFn: () => api.get<PortfolioValuation>(`/portfolios/analytics/valuation?${params.toString()}`),
  });
}

export function usePortfolioAllocation(portfolioId: string | null, unassigned = false) {
  const params = scopeParams({ portfolioId, unassigned });
  return useQuery({
    queryKey: ["portfolio", "analytics", "allocation", scopeKeyPart({ portfolioId, unassigned })] as const,
    queryFn: () => api.get<PortfolioAllocation>(`/portfolios/analytics/allocation?${params.toString()}`),
  });
}

export interface PortfolioPerformanceFilters {
  portfolio_id?: string | null;
  unassigned?: boolean;
  date_from?: string;
  date_to?: string;
}

export function usePortfolioPerformance(filters: PortfolioPerformanceFilters = {}) {
  const params = scopeParams({ portfolioId: filters.portfolio_id, unassigned: filters.unassigned });
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  return useQuery({
    queryKey: ["portfolio", "analytics", "performance", filters] as const,
    queryFn: () => api.get<PortfolioPerformance>(`/portfolios/analytics/performance?${params.toString()}`),
  });
}

/** Riepilogo di ogni Portfolio del workspace in una sola chiamata (lista
 * della Panoramica Investimenti) — mai N chiamate separate, una per
 * portfolio. */
export function usePortfolioSummaries() {
  return useQuery({
    queryKey: ["portfolio", "analytics", "summary"] as const,
    queryFn: () => api.get<PortfolioSummaryList>("/portfolios/analytics/summary"),
  });
}

export interface PortfolioPositionsFilters extends PortfolioScope {
  includeClosed?: boolean;
}

/** Valore attuale e rendimento per singola posizione (tabella Posizioni,
 * redesign) — mai calcolato client-side (richiede `fx_rate_service`,
 * solo il backend puo' convertire correttamente prezzo/posizione in
 * valute diverse). */
export function usePortfolioPositions(filters: PortfolioPositionsFilters = {}) {
  const params = scopeParams(filters);
  if (filters.includeClosed) params.set("include_closed", "true");
  return useQuery({
    queryKey: [
      "portfolio",
      "analytics",
      "positions",
      scopeKeyPart(filters),
      filters.includeClosed ?? false,
    ] as const,
    queryFn: () => api.get<PortfolioPositions>(`/portfolios/analytics/positions?${params.toString()}`),
  });
}

export interface RealizedPositionsFilters extends PortfolioScope {
  assetId?: string;
  accountId?: string;
  limit: number;
  offset: number;
}

/** Vista "Utile realizzato": ogni posizione con `realized_pl != 0`, aperta
 * o chiusa che sia (mai solo "posizioni chiuse" — una posizione ancora
 * aperta puo' avere un residuo di P&L realizzato da vendite parziali
 * passate, la somma della lista deve coincidere col numero mostrato sulla
 * card KPI). Riusa lo stesso endpoint di `usePortfolioPositions`, solo con
 * `realized_only`/paginazione — mai un endpoint nuovo. */
export function useRealizedPositions(filters: RealizedPositionsFilters) {
  const params = scopeParams(filters);
  params.set("realized_only", "true");
  if (filters.assetId) params.set("asset_id", filters.assetId);
  if (filters.accountId) params.set("financial_account_id", filters.accountId);
  params.set("limit", String(filters.limit));
  params.set("offset", String(filters.offset));
  return useQuery({
    queryKey: [
      "portfolio",
      "analytics",
      "positions",
      "realized",
      scopeKeyPart(filters),
      filters.assetId ?? "",
      filters.accountId ?? "",
      filters.limit,
      filters.offset,
    ] as const,
    queryFn: () => api.get<PortfolioPositions>(`/portfolios/analytics/positions?${params.toString()}`),
  });
}

/** docs/SPEC_STOCK_PRICE.md: mentre una vista portfolio-wide (Panoramica
 * Investimenti, dettaglio Portfolio) resta montata, ritrigger automatico in
 * background dello STESSO job del bottone "Aggiorna ora" quando l'ultimo
 * refresh e' piu' vecchio di `portfolio_refresh_interval_seconds` del
 * profilo attivo — mai un fetch sincrono per-asset qui: si riusa
 * l'infrastruttura job/dedup-guard gia' esistente (`useTriggerMarketData
 * Refresh`, gia' idempotente lato server). Il polling di
 * `useMarketDataRefreshStatus` stesso E' il meccanismo di "re-arm", nessun
 * timer manuale da gestire. Nessun profilo attivo = no-op (market data
 * resta sempre opzionale, DoD M09). */
export function usePortfolioMarketDataAutoRefresh(): { isRefreshing: boolean } {
  const queryClient = useQueryClient();
  const profiles = useMarketDataProfiles();
  const activeProfile = profiles.data?.find((p) => p.is_active) ?? null;
  const idlePollMs = activeProfile ? activeProfile.portfolio_refresh_interval_seconds * 1000 : undefined;
  const status = useMarketDataRefreshStatus(idlePollMs);
  const triggerRefresh = useTriggerMarketDataRefresh();
  const previousStatusRef = useRef<string | null>(null);

  useEffect(() => {
    if (!activeProfile || status.isLoading) return;
    const lastRun = status.data;
    const isStale =
      !lastRun ||
      (lastRun.status !== "running" &&
        Date.now() - new Date(lastRun.finished_at ?? lastRun.started_at).getTime() >=
          activeProfile.portfolio_refresh_interval_seconds * 1000);

    if (isStale && !triggerRefresh.isPending) {
      triggerRefresh.mutate();
    }
    if (previousStatusRef.current === "running" && lastRun?.status !== "running") {
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    }
    previousStatusRef.current = lastRun?.status ?? null;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reagisce solo al cambio di stato/profilo, non a triggerRefresh (nuova identita' mutation ad ogni render)
  }, [status.data, status.isLoading, activeProfile]);

  return { isRefreshing: status.data?.status === "running" };
}

/** Trigger manuale dello snapshot (DoD M09) — job async, nessun canale di
 * progresso live (stesso principio del refresh prezzi). */
export function useTriggerSnapshotRebuild() {
  return useMutation({
    mutationFn: () => api.post<SnapshotRebuildTriggered>("/portfolios/snapshots/rebuild"),
  });
}

/** Stato persistente dell'ultimo ricalcolo (manuale o cron) — stesso
 * principio di useMarketDataRefreshStatus (features/settings/market-data/api.ts). */
export function useSnapshotRebuildStatus() {
  return useQuery({
    queryKey: ["portfolio", "snapshots", "status"] as const,
    queryFn: () => api.get<JobRun | null>("/portfolios/snapshots/status"),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 3000 : false),
  });
}

/** Trigger della ricostruzione dell'INTERO storico patrimonio disponibile
 * (storico patrimonio ricostruito, FETTA 3) — a differenza di
 * `useTriggerSnapshotRebuild` (solo lo snapshot di OGGI, secondi), questo
 * job puo' impiegare minuti/ore (fase prezzi storici inclusa): nessun
 * `date_from` esplicito da qui, "Ricostruisci storico" ricostruisce sempre
 * tutto cio' che e' disponibile — un backfill scoped e' innescato solo
 * automaticamente a fine import. */
export function useTriggerSnapshotBackfill() {
  return useMutation({
    mutationFn: () => api.post<SnapshotBackfillTriggered>("/portfolios/snapshots/backfill"),
  });
}

/** Stato persistente dell'ultimo backfill (manuale o automatico a fine
 * import) — stesso principio di `useSnapshotRebuildStatus`, `job_kind`
 * diverso (`snapshot_backfill`, mai lo stesso job di "Ricalcola adesso"). */
export function useSnapshotBackfillStatus() {
  return useQuery({
    queryKey: ["portfolio", "snapshots", "backfill", "status"] as const,
    queryFn: () => api.get<JobRun | null>("/portfolios/snapshots/backfill/status"),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 3000 : false),
  });
}
