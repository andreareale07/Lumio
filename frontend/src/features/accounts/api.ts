import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import type { AccountType, FinancialAccount } from "../../types/api";

export const accountsKey = ["accounts"] as const;

export function useAccounts() {
  return useQuery({
    queryKey: accountsKey,
    queryFn: () => api.get<FinancialAccount[]>("/accounts"),
  });
}

export interface CreateAccountInput {
  name: string;
  account_type: AccountType;
  currency: string;
}

export function useCreateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateAccountInput) => api.post<FinancialAccount>("/accounts", input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accountsKey }),
  });
}

export function useSetAccountActive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      api.patch<FinancialAccount>(`/accounts/${id}`, { is_active: isActive }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accountsKey }),
  });
}
