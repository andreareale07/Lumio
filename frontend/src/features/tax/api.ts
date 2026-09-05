import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import { buildQueryString } from "../../lib/queryString";
import type {
  AssetTaxClassification,
  LossPocket,
  RealizedEventsPage,
  TaxableGains,
  TaxEventOverride,
  TaxEventOverrideInput,
  TaxJurisdiction,
  TaxLossOpening,
  TaxLossOpeningCreate,
  TaxRegimePeriod,
  TaxRulesetDetail,
  TaxRulesetSummary,
  WorkspaceTaxResidence,
} from "../../types/api";

// SPEC_TAX_REGIME.md FETTA 1: nessun canale realtime, dato sempre derivato a
// lettura — invalidare per query key basta, nessuna sottoscrizione SSE come
// per gli import/job.

export const taxJurisdictionsKey = ["tax", "jurisdictions"] as const;
export const taxRulesetsKey = ["tax", "rulesets"] as const;
export const taxRulesetKey = (on: string) => ["tax", "ruleset", on] as const;
export const taxResidencesKey = ["tax", "residences"] as const;
export const taxRegimePeriodsKey = (accountId: string) => ["tax", "accounts", accountId, "regimes"] as const;
export const taxRegimeResolveKey = (accountId: string, on: string) =>
  ["tax", "regimes", "resolve", accountId, on] as const;
export const taxAssetClassificationsKey = (on: string) => ["tax", "asset-classifications", on] as const;
export const taxLossOpeningsKey = ["tax", "loss-pocket", "openings"] as const;
export const taxLossPocketKey = (on: string) => ["tax", "loss-pocket", on] as const;

export function useTaxJurisdictions() {
  return useQuery({
    queryKey: taxJurisdictionsKey,
    queryFn: () => api.get<TaxJurisdiction[]>("/tax/jurisdictions"),
  });
}

export function useTaxRulesets() {
  return useQuery({
    queryKey: taxRulesetsKey,
    queryFn: () => api.get<TaxRulesetSummary[]>("/tax/rulesets"),
  });
}

/** `on`: data ISO (YYYY-MM-DD) — la "pagina informativa" delle regole
 * vigenti a quella data, unica fonte anche per i picker di regime/classe
 * asset (`regimes`/`asset_classes` nella response). */
export function useTaxRuleset(on: string) {
  return useQuery({
    queryKey: taxRulesetKey(on),
    queryFn: () => api.get<TaxRulesetDetail>(`/tax/ruleset${buildQueryString({ on })}`),
    enabled: !!on,
  });
}

export function useTaxResidences() {
  return useQuery({
    queryKey: taxResidencesKey,
    queryFn: () => api.get<WorkspaceTaxResidence[]>("/tax/residences"),
  });
}

export function useUpsertTaxResidence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ fiscal_year, jurisdiction_code }: { fiscal_year: number; jurisdiction_code: string }) =>
      api.put<WorkspaceTaxResidence>(`/tax/residences/${fiscal_year}`, { fiscal_year, jurisdiction_code }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taxResidencesKey }),
  });
}

export function useDeleteTaxResidence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (fiscalYear: number) => api.delete<void>(`/tax/residences/${fiscalYear}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taxResidencesKey }),
  });
}

export function useTaxRegimePeriods(accountId: string | undefined) {
  return useQuery({
    queryKey: taxRegimePeriodsKey(accountId ?? ""),
    queryFn: () => api.get<TaxRegimePeriod[]>(`/tax/accounts/${accountId}/regimes`),
    enabled: !!accountId,
  });
}

export function useCreateTaxRegimePeriod(accountId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { regime_code: string; effective_from: string }) =>
      api.post<TaxRegimePeriod>(`/tax/accounts/${accountId}/regimes`, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taxRegimePeriodsKey(accountId) }),
  });
}

export function useDeleteTaxRegimePeriod(accountId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (periodId: string) => api.delete<void>(`/tax/accounts/${accountId}/regimes/${periodId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taxRegimePeriodsKey(accountId) }),
  });
}

export function useResolveTaxRegime(accountId: string | undefined, on: string) {
  return useQuery({
    queryKey: taxRegimeResolveKey(accountId ?? "", on),
    queryFn: () =>
      api.get<{ regime_code: string | null }>(`/tax/regimes/resolve${buildQueryString({ account_id: accountId, on })}`),
    enabled: !!accountId && !!on,
  });
}

export function useTaxAssetClassifications(on: string) {
  return useQuery({
    queryKey: taxAssetClassificationsKey(on),
    queryFn: () => api.get<AssetTaxClassification[]>(`/tax/asset-classifications${buildQueryString({ on })}`),
    enabled: !!on,
  });
}

export function useSetTaxAssetClassification(on: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ assetId, asset_class }: { assetId: string; asset_class: string }) =>
      api.put<AssetTaxClassification>(`/tax/asset-classifications/${assetId}${buildQueryString({ on })}`, {
        asset_class,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taxAssetClassificationsKey(on) }),
  });
}

export function useDeleteTaxAssetClassification(on: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assetId: string) =>
      api.delete<void>(`/tax/asset-classifications/${assetId}${buildQueryString({ on })}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taxAssetClassificationsKey(on) }),
  });
}

export function useTaxLossOpenings() {
  return useQuery({
    queryKey: taxLossOpeningsKey,
    queryFn: () => api.get<TaxLossOpening[]>("/tax/loss-pocket/openings"),
  });
}

function invalidateLossPocket(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: taxLossOpeningsKey });
  queryClient.invalidateQueries({ queryKey: ["tax", "loss-pocket"] });
  queryClient.invalidateQueries({ queryKey: ["tax", "taxable-gains"] });
}

export function useCreateTaxLossOpening() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: TaxLossOpeningCreate) => api.post<TaxLossOpening>("/tax/loss-pocket/openings", input),
    onSuccess: () => invalidateLossPocket(queryClient),
  });
}

export function useDeleteTaxLossOpening() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/tax/loss-pocket/openings/${id}`),
    onSuccess: () => invalidateLossPocket(queryClient),
  });
}

/** `on`: data ISO — lo zainetto vigente a quella data (scadenze/conversioni
 * risolte dal backend, mai ricalcolate qui). */
export function useLossPocket(on: string) {
  return useQuery({
    queryKey: taxLossPocketKey(on),
    queryFn: () => api.get<LossPocket>(`/tax/loss-pocket${buildQueryString({ on })}`),
    enabled: !!on,
  });
}

export const taxTaxableGainsKey = (on: string) => ["tax", "taxable-gains", on] as const;

/** FETTA 2: compensazione progressiva delle plusvalenze realizzate contro
 * lo zainetto — vista separata da `useLossPocket` (quella resta la vista
 * onesta "quanto ho disponibile prima di consumarlo"). */
export function useTaxableGains(on: string) {
  return useQuery({
    queryKey: taxTaxableGainsKey(on),
    queryFn: () => api.get<TaxableGains>(`/tax/taxable-gains${buildQueryString({ on })}`),
    enabled: !!on,
  });
}

export interface RealizedEventsFilters {
  on: string;
  asset_id?: string;
  financial_account_id?: string;
  excluded_only?: boolean;
  limit: number;
  offset: number;
}

export const taxRealizedEventsKey = (filters: RealizedEventsFilters) => ["tax", "realized-events", filters] as const;

/** Elenco paginato/filtrabile degli eventi realizzati (inclusi quelli
 * esclusi, con motivo) — usato dalla pagina dedicata
 * `/investments/tax/realized-events` per scegliere quale evento correggere
 * con un override (FETTA 2, "override per singolo evento"). Il backend
 * calcola per intero in memoria e pagina solo la vista: `total` è un
 * conteggio esatto, non un'euristica. */
export function useRealizedEvents(filters: RealizedEventsFilters) {
  return useQuery({
    queryKey: taxRealizedEventsKey(filters),
    queryFn: () => api.get<RealizedEventsPage>(`/tax/realized-events${buildQueryString(filters)}`),
    enabled: !!filters.on,
  });
}

function invalidateRealizedEvents(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["tax", "realized-events"] });
  queryClient.invalidateQueries({ queryKey: ["tax", "loss-pocket"] });
  queryClient.invalidateQueries({ queryKey: ["tax", "taxable-gains"] });
}

export function useSetEventOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      lotTransactionId,
      sellTransactionId,
      input,
    }: {
      lotTransactionId: string;
      sellTransactionId: string;
      input: TaxEventOverrideInput;
    }) => api.put<TaxEventOverride>(`/tax/realized-events/${lotTransactionId}/${sellTransactionId}/override`, input),
    onSuccess: () => invalidateRealizedEvents(queryClient),
  });
}

export function useDeleteEventOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ lotTransactionId, sellTransactionId }: { lotTransactionId: string; sellTransactionId: string }) =>
      api.delete<void>(`/tax/realized-events/${lotTransactionId}/${sellTransactionId}/override`),
    onSuccess: () => invalidateRealizedEvents(queryClient),
  });
}
