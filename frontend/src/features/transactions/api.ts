import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import { buildQueryString } from "../../lib/queryString";
import type {
  Classification,
  Transaction,
  TransactionListSummary,
  TransactionMerchants,
  TransactionReviewSummary,
} from "../../types/api";

export interface TransactionFilters {
  /** Un valore o piu' valori (OR): la lista accetta selezione multipla. */
  financial_account_id?: string | string[];
  category_id?: string | string[];
  /** Match esatto sul merchant; `no_merchant` per le righe senza merchant. */
  merchant?: string | string[];
  no_merchant?: boolean;
  transaction_type?: string | string[];
  date_from?: string;
  date_to?: string;
  needs_review?: boolean;
  import_id?: string;
  limit?: number;
  offset?: number;
}

export const transactionsKey = (filters: TransactionFilters) => ["transactions", filters] as const;
export const classificationsKey = (transactionId: string) => ["classifications", transactionId] as const;

export function useTransactions(filters: TransactionFilters, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: transactionsKey(filters),
    queryFn: () => api.get<Transaction[]>(`/transactions${buildQueryString(filters)}`),
    enabled: options.enabled ?? true,
  });
}

/** SPEC §43 ("319 classificati, 8 da verificare"): conteggio aggregato lato
 * server, mai calcolato scaricando le righe — usato per il badge "da
 * verificare" (TransactionsPage) e per il riepilogo a fine import
 * (ImportsPage), con gli stessi filtri di useTransactions cosi' i due numeri
 * restano coerenti tra loro. */
export function useTransactionReviewSummary(
  filters: { financial_account_id?: string; import_id?: string } = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: ["transactions", "review-summary", filters],
    queryFn: () => api.get<TransactionReviewSummary>(`/transactions/review-summary${buildQueryString(filters)}`),
    enabled: options.enabled ?? true,
  });
}

/** Conteggio + entrate/uscite delle righe che `useTransactions` restituisce
 * con gli stessi filtri (senza paginazione). */
export function useTransactionListSummary(filters: Omit<TransactionFilters, "limit" | "offset">) {
  return useQuery({
    queryKey: ["transactions", "list-summary", filters],
    queryFn: () => api.get<TransactionListSummary>(`/transactions/summary${buildQueryString(filters)}`),
  });
}

/** Merchant con numero di movimenti (piu' frequenti prima), con ricerca sul
 * server: alimenta il selettore del filtro merchant. */
export function useTransactionMerchants(query: string, limit = 10) {
  const q = query.trim();
  return useQuery({
    queryKey: ["transactions", "merchants", q, limit],
    queryFn: () => api.get<TransactionMerchants>(`/transactions/merchants${buildQueryString({ q, limit })}`),
    placeholderData: (previous) => previous,
  });
}

export function useClassifications(transactionId: string | null) {
  return useQuery({
    queryKey: classificationsKey(transactionId ?? ""),
    queryFn: () => api.get<Classification[]>(`/transactions/${transactionId}/classifications`),
    enabled: !!transactionId,
  });
}

export function useUpdateTransactionCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, categoryId }: { id: string; categoryId: string | null }) =>
      api.patch<Transaction>(`/transactions/${id}`, { category_id: categoryId }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: classificationsKey(variables.id) });
      queryClient.invalidateQueries({ queryKey: ["rules", "suggestions"] });
    },
  });
}
