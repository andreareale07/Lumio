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
  iban?: string | null;
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

export interface UpdateAccountInput {
  id: string;
  name?: string;
  account_type?: AccountType;
  currency?: string;
  iban?: string | null;
}

/** Serve soprattutto a correggere il `account_type` scelto in creazione
 * (es. un conto Trade Republic usato per la spesa quotidiana, non solo per
 * investire): l'`account_type` determina in quale bucket del dashboard
 * finisce il saldo (Liquidità vs Investimenti, milestone 08), quindi deve
 * poter essere corretto senza ricreare il conto. */
export function useUpdateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: UpdateAccountInput) => api.patch<FinancialAccount>(`/accounts/${id}`, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accountsKey }),
  });
}
