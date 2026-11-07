import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../../lib/apiClient";
import type {
  BankAccountUpdate,
  BankConnection,
  BankConnectionAccount,
  BankDisconnectResult,
  BankInstitution,
  OpenBankingCredential,
  OpenBankingStatus,
  Uuid,
} from "../../../types/api";

export const openBankingStatusKey = ["open-banking", "status"] as const;
export const bankConnectionsKey = ["open-banking", "connections"] as const;

export function useOpenBankingStatus() {
  return useQuery({
    queryKey: openBankingStatusKey,
    queryFn: () => api.get<OpenBankingStatus>("/open-banking"),
  });
}

export function useGenerateCredentials() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<OpenBankingCredential>("/open-banking/credentials"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: openBankingStatusKey }),
  });
}

export function useSetApplicationId() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (applicationId: string) =>
      api.put<OpenBankingCredential>("/open-banking/credentials/application-id", {
        application_id: applicationId,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: openBankingStatusKey }),
  });
}

export function useDeleteCredentials() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete<void>("/open-banking/credentials"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["open-banking"] }),
  });
}

export function useInstitutions(country: string, enabled: boolean) {
  return useQuery({
    queryKey: ["open-banking", "institutions", country] as const,
    queryFn: () => api.get<BankInstitution[]>(`/open-banking/institutions?country=${encodeURIComponent(country)}`),
    enabled,
    staleTime: 10 * 60 * 1000,
  });
}

/** Ritorna l'URL di autorizzazione della banca: chi chiama deve navigare il
 * BROWSER li' (`window.location.assign`), come per Google. */
export function useStartConnection() {
  return useMutation({
    mutationFn: (bank: { aspsp_name: string; aspsp_country: string }) =>
      api.post<{ authorize_url: string }>("/open-banking/connections", { ...bank, psu_type: "personal" }),
  });
}

const SYNC_POLL_MS = 2500;

/** Elenco delle banche collegate. Si aggiorna da solo (ogni 2,5 s) finche' una
 * sincronizzazione e' in corso lato server o `pollWhile()` lo richiede (sync
 * appena accodata, che il worker non ha ancora preso in carico). */
export function useBankConnections(options: { enabled?: boolean; pollWhile?: () => boolean } = {}) {
  const { enabled = true, pollWhile } = options;
  return useQuery({
    queryKey: bankConnectionsKey,
    queryFn: () => api.get<BankConnection[]>("/open-banking/connections"),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((connection) => connection.sync_running) || pollWhile?.() ? SYNC_POLL_MS : false,
  });
}

export function useUpdateBankAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      connectionId,
      accountId,
      update,
    }: {
      connectionId: Uuid;
      accountId: Uuid;
      update: BankAccountUpdate;
    }) =>
      api.patch<BankConnectionAccount>(
        `/open-banking/connections/${connectionId}/accounts/${accountId}`,
        update,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: bankConnectionsKey });
      // Un conto creato al volo compare anche nell'elenco dei conti.
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

export function useSyncConnection() {
  return useMutation({
    mutationFn: (connectionId: Uuid) =>
      api.post<{ status: "queued" }>(`/open-banking/connections/${connectionId}/sync`),
  });
}

/** "Rileggi storico": azzera il cursore del conto e accoda una sync che rilegge tutto. */
export function useResyncHistory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ connectionId, accountId }: { connectionId: Uuid; accountId: Uuid }) =>
      api.post<{ status: "queued" }>(
        `/open-banking/connections/${connectionId}/accounts/${accountId}/resync-history`,
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: bankConnectionsKey }),
  });
}

export function useDisconnectBank() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ connectionId, deleteData }: { connectionId: Uuid; deleteData: boolean }) =>
      api.delete<BankDisconnectResult>(
        `/open-banking/connections/${connectionId}${deleteData ? "?delete_data=true" : ""}`,
      ),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: bankConnectionsKey });
      if (result.deleted_transactions > 0) {
        // Movimenti eliminati: movimenti, conti e analisi vanno riallineati.
        void queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "open-banking" });
      }
    },
  });
}
