import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import { buildQueryString } from "../../lib/queryString";
import type {
  AnalyticsBalanceHistory,
  AnalyticsBalances,
  AnalyticsCashFlow,
  AnalyticsCategoryBreakdown,
  AnalyticsDirection,
  AnalyticsGranularity,
  AnalyticsMerchantBreakdown,
  AnalyticsSummary,
  NetWorthHistory,
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
