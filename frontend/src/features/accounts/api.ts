import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import type { AccountType, FinancialAccount, IbanHistoryEntry } from "../../types/api";

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
  classification_language?: "it" | "en" | null;
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
  classification_language?: "it" | "en" | null;
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

function ibanHistoryKey(accountId: string) {
  return ["accounts", accountId, "iban-history"] as const;
}

/** Milestone 09.5c: IBAN storici di un conto — aggiunta MANUALE, per chi
 * conosce gia' un IBAN precedente quando imposta il conto per la prima
 * volta (distinta dalla storicizzazione automatica di useUpdateAccount,
 * che scatta solo quando il campo cambia dentro l'app). */
export function useIbanHistory(accountId: string | null) {
  return useQuery({
    queryKey: ibanHistoryKey(accountId ?? ""),
    queryFn: () => api.get<IbanHistoryEntry[]>(`/accounts/${accountId}/iban-history`),
    enabled: !!accountId,
  });
}

export function useAddIbanHistory(accountId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (iban: string) =>
      api.post<IbanHistoryEntry>(`/accounts/${accountId}/iban-history`, { iban }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ibanHistoryKey(accountId) }),
  });
}

export function useDeleteIbanHistory(accountId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (historyId: string) =>
      api.delete<void>(`/accounts/${accountId}/iban-history/${historyId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ibanHistoryKey(accountId) }),
  });
}
