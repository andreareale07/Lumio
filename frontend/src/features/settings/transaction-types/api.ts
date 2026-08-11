import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../../lib/apiClient";
import type { TransactionType, TransactionTypeLabel, TransactionTypeMappingUpsertResult } from "../../../types/api";

export const usedParserTypesKey = ["settings", "transaction-types", "parsers"] as const;

export function useUsedParserTypes() {
  return useQuery({
    queryKey: usedParserTypesKey,
    queryFn: () => api.get<string[]>("/settings/transaction-types/parsers"),
  });
}

function labelsKey(parserType: string) {
  return ["settings", "transaction-types", parserType, "labels"] as const;
}

export function useTransactionTypeLabels(parserType: string | null) {
  return useQuery({
    queryKey: labelsKey(parserType ?? ""),
    queryFn: () => api.get<TransactionTypeLabel[]>(`/settings/transaction-types/${encodeURIComponent(parserType!)}/labels`),
    enabled: !!parserType,
  });
}

/** PUT salva l'override E applica subito la rimappatura retroattiva
 * (sincrona lato backend, vedi transaction_type_mapping_service.py) — il
 * risultato torna nella stessa risposta, nessun polling necessario. */
export function useUpsertTransactionTypeMapping(parserType: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sourceTypeRaw, transactionType }: { sourceTypeRaw: string; transactionType: TransactionType }) =>
      api.put<TransactionTypeMappingUpsertResult>(
        `/settings/transaction-types/${encodeURIComponent(parserType)}/labels/${encodeURIComponent(sourceTypeRaw)}`,
        { transaction_type: transactionType },
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: labelsKey(parserType) }),
  });
}

export function useDeleteTransactionTypeMapping(parserType: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceTypeRaw: string) =>
      api.delete<void>(
        `/settings/transaction-types/${encodeURIComponent(parserType)}/labels/${encodeURIComponent(sourceTypeRaw)}`,
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: labelsKey(parserType) }),
  });
}
