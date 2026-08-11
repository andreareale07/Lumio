import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../../lib/apiClient";
import type {
  MarketDataConnectionCheckRequest,
  MarketDataProfile,
  MarketDataProfileCreate,
  MarketDataProfileUpdate,
  MarketDataRefreshTriggered,
  MarketDataTestConnectionResult,
} from "../../../types/api";

export const marketDataProfilesKey = ["settings", "market-data", "profiles"] as const;

export function useMarketDataProfiles() {
  return useQuery({
    queryKey: marketDataProfilesKey,
    queryFn: () => api.get<MarketDataProfile[]>("/settings/market-data/profiles"),
  });
}

function invalidateProfiles(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: marketDataProfilesKey });
}

export function useCreateMarketDataProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: MarketDataProfileCreate) =>
      api.post<MarketDataProfile>("/settings/market-data/profiles", input),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useUpdateMarketDataProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: MarketDataProfileUpdate & { id: string }) =>
      api.patch<MarketDataProfile>(`/settings/market-data/profiles/${id}`, input),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useDeleteMarketDataProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/settings/market-data/profiles/${id}`),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useActivateMarketDataProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<MarketDataProfile>(`/settings/market-data/profiles/${id}/activate`),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useDeactivateMarketData() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/settings/market-data/deactivate"),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useTestDraftMarketDataConnection() {
  return useMutation({
    mutationFn: (input: MarketDataConnectionCheckRequest) =>
      api.post<MarketDataTestConnectionResult>("/settings/market-data/test", input),
  });
}

export function useTestSavedMarketDataProfile() {
  return useMutation({
    mutationFn: (id: string) =>
      api.post<MarketDataTestConnectionResult>(`/settings/market-data/profiles/${id}/test`),
  });
}

/** Trigger manuale (DoD M09): accoda il job di refresh invece di aspettare
 * il cron notturno — utile subito dopo aver configurato/attivato un
 * profilo. Nessun canale di progresso live: si invalidano semplicemente le
 * query dei prezzi dopo un breve ritardo (vedi MarketDataSettingsPage). */
export function useTriggerMarketDataRefresh() {
  return useMutation({
    mutationFn: () => api.post<MarketDataRefreshTriggered>("/settings/market-data/refresh"),
  });
}
