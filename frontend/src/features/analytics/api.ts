import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import { buildQueryString } from "../../lib/queryString";
import type {
  AnalyticsBalanceHistory,
  AnalyticsBalances,
  AnalyticsCashFlow,
  AnalyticsCategoryBreakdown,
  AnalyticsCategoryTrend,
  AnalyticsDirection,
  AnalyticsGranularity,
  AnalyticsMerchantBreakdown,
  AnalyticsSummary,
  AnomalyList,
  DetectionOverride,
  DetectionOverrideType,
  NetWorthHistory,
  RecurringSeriesList,
} from "../../types/api";

export interface PeriodFilters {
  date_from?: string;
  date_to?: string;
  currency?: string;
  financial_account_id?: string;
}

export interface GranularityFilters extends PeriodFilters {
  granularity?: AnalyticsGranularity;
  category_id?: string;
}

export interface BreakdownFilters extends PeriodFilters {
  direction?: AnalyticsDirection;
  category_id?: string;
  /** Redesign Spese/Entrate (FETTA 1): raggruppa per FOGLIA dentro questo
   * padre invece che per categoria di primo livello — usato dalla riga
   * espansa della gerarchia categorie, mai insieme a `category_id` (semantica
   * diversa: quello e' un filtro puro, questo cambia il livello di
   * raggruppamento). */
  parent_id?: string;
}

export const summaryKey = (filters: PeriodFilters) => ["analytics", "summary", filters] as const;
export const balancesKey = (filters: { currency?: string; as_of?: string }) =>
  ["analytics", "balances", filters] as const;
export const balanceHistoryKey = (filters: GranularityFilters) =>
  ["analytics", "balance-history", filters] as const;
export const cashFlowKey = (filters: GranularityFilters) => ["analytics", "cash-flow", filters] as const;
export const byCategoryKey = (filters: BreakdownFilters) => ["analytics", "by-category", filters] as const;
export const byMerchantKey = (filters: BreakdownFilters) => ["analytics", "by-merchant", filters] as const;

export function useAnalyticsSummary(filters: PeriodFilters) {
  return useQuery({
    queryKey: summaryKey(filters),
    queryFn: () => api.get<AnalyticsSummary>(`/analytics/summary${buildQueryString(filters)}`),
  });
}

export function useAnalyticsBalances(filters: { currency?: string; as_of?: string } = {}) {
  return useQuery({
    queryKey: balancesKey(filters),
    queryFn: () => api.get<AnalyticsBalances>(`/analytics/balances${buildQueryString(filters)}`),
  });
}

export function useAnalyticsBalanceHistory(filters: GranularityFilters) {
  return useQuery({
    queryKey: balanceHistoryKey(filters),
    queryFn: () =>
      api.get<AnalyticsBalanceHistory>(`/analytics/balance-history${buildQueryString(filters)}`),
  });
}

export function useAnalyticsCashFlow(filters: GranularityFilters, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: cashFlowKey(filters),
    queryFn: () => api.get<AnalyticsCashFlow>(`/analytics/cash-flow${buildQueryString(filters)}`),
    enabled: options.enabled ?? true,
  });
}

export function useAnalyticsByCategory(filters: BreakdownFilters, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: byCategoryKey(filters),
    queryFn: () =>
      api.get<AnalyticsCategoryBreakdown>(`/analytics/by-category${buildQueryString(filters)}`),
    enabled: options.enabled ?? true,
  });
}

export function useAnalyticsByMerchant(filters: BreakdownFilters, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: byMerchantKey(filters),
    queryFn: () =>
      api.get<AnalyticsMerchantBreakdown>(`/analytics/by-merchant${buildQueryString(filters)}`),
    enabled: options.enabled ?? true,
  });
}

export const categoryTrendKey = (filters: GranularityFilters & { direction?: AnalyticsDirection; parent_id?: string }) =>
  ["analytics", "category-trend", filters] as const;

/** Matrice bucket x categoria (redesign Spese/Entrate, FETTA 1) — UNA
 * chiamata al posto di N `useAnalyticsCashFlow({category_id})` sequenziali,
 * usata per le sparkline per riga e lo scostamento "vs tipico" della
 * gerarchia categorie. */
export function useAnalyticsCategoryTrend(
  filters: GranularityFilters & { direction?: AnalyticsDirection; parent_id?: string },
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: categoryTrendKey(filters),
    queryFn: () => api.get<AnalyticsCategoryTrend>(`/analytics/category-trend${buildQueryString(filters)}`),
    enabled: options.enabled ?? true,
  });
}

export const netWorthHistoryKey = (filters: PeriodFilters) => ["analytics", "net-worth-history", filters] as const;

/** A differenza di `useAnalyticsBalanceHistory` (sola liquidita',
 * ricostruita a ritroso dalle transazioni), legge dagli snapshot gia'
 * scritti (`net_worth_snapshots`) e include gli investimenti a valore di
 * mercato — nessun parametro `granularity`, il backend ritorna sempre la
 * serie giornaliera grezza degli snapshot nel range (stesso principio di
 * `usePortfolioPerformance`). */
export function useAnalyticsNetWorthHistory(filters: PeriodFilters) {
  return useQuery({
    queryKey: netWorthHistoryKey(filters),
    queryFn: () => api.get<NetWorthHistory>(`/analytics/net-worth-history${buildQueryString(filters)}`),
  });
}

// --- Ricorrenze e anomalie (piano synchronous-chasing-pike.md, FETTA 2) ---

export interface RecurringFilters {
  direction?: AnalyticsDirection;
  currency?: string;
  as_of?: string;
}

export interface AnomalyFilters extends PeriodFilters {
  direction?: AnalyticsDirection;
  limit?: number;
}

export const recurringKey = (filters: RecurringFilters) => ["analytics", "recurring", filters] as const;
export const anomaliesKey = (filters: AnomalyFilters) => ["analytics", "anomalies", filters] as const;

/** SENZA `date_from`/`date_to` ne' `financial_account_id` — un solo mese
 * non puo' mai rilevare una ricorrenza, e il filtro conto spezzerebbe
 * esattamente la serie che si sposta da una carta all'altra (vedi il
 * docstring dell'endpoint sul backend). */
export function useRecurringSeries(filters: RecurringFilters, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: recurringKey(filters),
    queryFn: () => api.get<RecurringSeriesList>(`/analytics/recurring${buildQueryString(filters)}`),
    enabled: options.enabled ?? true,
  });
}

export function useAnomalies(filters: AnomalyFilters, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: anomaliesKey(filters),
    queryFn: () => api.get<AnomalyList>(`/analytics/anomalies${buildQueryString(filters)}`),
    enabled: options.enabled ?? true,
  });
}

export interface DetectionOverrideInput {
  override_type: DetectionOverrideType;
  series_key?: string;
  transaction_id?: string;
  decision?: "ignored";
}

/** "Ignora questo segnale" (CLAUDE.md: le correzioni manuali hanno sempre
 * priorita' sull'AI) — invalida ENTRAMBE le key (ricorrenze e anomalie),
 * mai una sola: un override su una serie ricorrente puo' far sparire anche
 * le sue `series_deviation` dalla lista anomalie. */
export function useDismissDetection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: DetectionOverrideInput) =>
      api.post<DetectionOverride>("/analytics/detection-overrides", { decision: "ignored", ...input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analytics", "recurring"] });
      queryClient.invalidateQueries({ queryKey: ["analytics", "anomalies"] });
    },
  });
}

/** "Annulla" — rimuove l'override, il segnale ricompare alla richiesta
 * successiva (nessuno stato "annullato" separato, vedi l'endpoint DELETE). */
export function useUndoDetectionOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (overrideId: string) => api.delete<void>(`/analytics/detection-overrides/${overrideId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analytics", "recurring"] });
      queryClient.invalidateQueries({ queryKey: ["analytics", "anomalies"] });
    },
  });
}
