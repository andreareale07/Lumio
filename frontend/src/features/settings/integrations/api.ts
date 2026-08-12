import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, getAccessToken } from "../../../lib/apiClient";
import type {
  ConnectUrlOut,
  GoogleExportRequest,
  GoogleExportTriggered,
  GoogleIntegration,
  JobRun,
  PickerToken,
  SetDriveFolderRequest,
} from "../../../types/api";

export const googleIntegrationKey = ["settings", "integrations", "google"] as const;
export const googleExportStatusKey = ["settings", "integrations", "google", "export-status"] as const;

export function useGoogleIntegration() {
  return useQuery({
    queryKey: googleIntegrationKey,
    queryFn: () => api.get<GoogleIntegration | null>("/integrations/google"),
  });
}

/** Ritorna l'URL di autorizzazione: chi chiama deve navigare il BROWSER lì
 * (`window.location.assign`), non trattarlo come una redirezione da
 * seguire via fetch — vedi `ConnectUrlOut` lato backend per il perché. */
export function useConnectGoogle() {
  return useMutation({
    mutationFn: () => api.get<ConnectUrlOut>("/integrations/google/connect"),
  });
}

export function useDisconnectGoogle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/integrations/google/disconnect"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: googleIntegrationKey }),
  });
}

export function useSetGoogleDriveFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SetDriveFolderRequest) =>
      api.post<GoogleIntegration>("/integrations/google/folder", input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: googleIntegrationKey }),
  });
}

/** Non un hook: serve on-demand solo nel momento in cui si apre il widget
 * Google Picker (connect wizard o "Cambia cartella"), non per il rendering
 * della pagina. */
export async function fetchGooglePickerToken(): Promise<PickerToken> {
  return api.get<PickerToken>("/integrations/google/picker-token");
}

export function useTriggerGoogleExport() {
  return useMutation({
    mutationFn: (input: GoogleExportRequest) =>
      api.post<GoogleExportTriggered>("/integrations/google/export", input),
  });
}

/** Stato persistente dell'ultimo export — sopravvive a un refresh pagina,
 * stesso principio di `useMarketDataRefreshStatus`. Polling leggero solo
 * mentre e' "running" (fallback se lo stream SSE si interrompe). */
export function useGoogleExportStatus() {
  return useQuery({
    queryKey: googleExportStatusKey,
    queryFn: () => api.get<JobRun | null>("/integrations/google/export-status"),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 3000 : false),
  });
}

export interface GoogleExportProgressEvent {
  event: string;
  stage?: string;
  progress?: number;
  message?: string;
}

/** Stesso pattern di `streamImportEvents` (fetch()+ReadableStream, non
 * EventSource: serve poter mandare l'header Authorization). */
export async function streamGoogleExportEvents(
  onEvent: (event: GoogleExportProgressEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(`${api.base}/integrations/google/export-events`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, "Impossibile connettersi al flusso di progresso", null);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const eventLine = chunk.split("\n").find((line) => line.startsWith("event:"));
      const dataLine = chunk.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      try {
        const data = JSON.parse(dataLine.slice(5).trim());
        onEvent({ event: eventLine?.slice(6).trim() ?? "message", ...data });
      } catch {
        // riga non-JSON (es. commento keep-alive): ignorata
      }
    }
  }
}
