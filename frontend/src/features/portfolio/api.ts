import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import type {
  Asset,
  AssetType,
  InvestmentTransaction,
  InvestmentTransactionType,
  JobRun,
  Portfolio,
  PortfolioAccountLink,
  PortfolioAllocation,
  PortfolioPerformance,
  PortfolioValuation,
  Position,
  SnapshotRebuildTriggered,
} from "../../types/api";

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

// --- Portfolios (aggregazione su piu' conti, SPEC §36) --------------------

export const portfoliosKey = ["portfolio", "portfolios"] as const;

export function usePortfolios() {
  return useQuery({ queryKey: portfoliosKey, queryFn: () => api.get<Portfolio[]>("/portfolios") });
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
  asset_id?: string;
  type?: InvestmentTransactionType;
  limit?: number;
  offset?: number;
}

export function useInvestmentTransactions(filters: InvestmentTransactionFilters = {}) {
  const params = new URLSearchParams();
  if (filters.financial_account_id) params.set("financial_account_id", filters.financial_account_id);
  if (filters.asset_id) params.set("asset_id", filters.asset_id);
  if (filters.type) params.set("type", filters.type);
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

export function portfolioValuationKey(portfolioId: string | null) {
  return ["portfolio", "analytics", "valuation", portfolioId ?? "all"] as const;
}

export function usePortfolioValuation(portfolioId: string | null) {
  const params = new URLSearchParams();
  if (portfolioId) params.set("portfolio_id", portfolioId);
  return useQuery({
    queryKey: portfolioValuationKey(portfolioId),
    queryFn: () => api.get<PortfolioValuation>(`/portfolios/analytics/valuation?${params.toString()}`),
  });
}

export function usePortfolioAllocation(portfolioId: string | null) {
  const params = new URLSearchParams();
  if (portfolioId) params.set("portfolio_id", portfolioId);
  return useQuery({
    queryKey: ["portfolio", "analytics", "allocation", portfolioId ?? "all"] as const,
    queryFn: () => api.get<PortfolioAllocation>(`/portfolios/analytics/allocation?${params.toString()}`),
  });
}

export interface PortfolioPerformanceFilters {
  portfolio_id?: string | null;
  date_from?: string;
  date_to?: string;
}

export function usePortfolioPerformance(filters: PortfolioPerformanceFilters = {}) {
  const params = new URLSearchParams();
  if (filters.portfolio_id) params.set("portfolio_id", filters.portfolio_id);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  return useQuery({
    queryKey: ["portfolio", "analytics", "performance", filters] as const,
    queryFn: () => api.get<PortfolioPerformance>(`/portfolios/analytics/performance?${params.toString()}`),
  });
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
