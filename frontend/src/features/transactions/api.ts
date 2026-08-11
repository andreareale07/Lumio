import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import type { Classification, Transaction } from "../../types/api";

export interface TransactionFilters {
  financial_account_id?: string;
  category_id?: string;
  transaction_type?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export const transactionsKey = (filters: TransactionFilters) => ["transactions", filters] as const;
export const classificationsKey = (transactionId: string) => ["classifications", transactionId] as const;

function buildQueryString(filters: TransactionFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useTransactions(filters: TransactionFilters, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: transactionsKey(filters),
    queryFn: () => api.get<Transaction[]>(`/transactions${buildQueryString(filters)}`),
    enabled: options.enabled ?? true,
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
