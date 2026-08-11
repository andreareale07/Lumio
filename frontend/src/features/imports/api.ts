import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, getAccessToken } from "../../lib/apiClient";
import type { ImportRecord, ImportUploadResponse, MappingConfig } from "../../types/api";

export const importsKey = ["imports"] as const;

export function useImports() {
  return useQuery({
    queryKey: importsKey,
    queryFn: () => api.get<ImportRecord[]>("/imports"),
  });
}

export function useUploadImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ accountId, file }: { accountId: string; file: File }) => {
      const form = new FormData();
      form.set("financial_account_id", accountId);
      form.set("file", file);
      return api.postForm<ImportUploadResponse>("/imports", form);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: importsKey }),
  });
}

export interface ConfirmImportInput {
  importId: string;
  mapping?: MappingConfig;
}

export function useConfirmImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ importId, mapping }: ConfirmImportInput) =>
      api.post<ImportRecord>(`/imports/${importId}/confirm`, mapping ? { mapping } : {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: importsKey }),
  });
}

export function useImport(importId: string | null) {
  return useQuery({
    queryKey: ["imports", importId],
    queryFn: () => api.get<ImportRecord>(`/imports/${importId}`),
    enabled: !!importId,
    refetchInterval: (query) => {
      // Fallback polling (SPEC_FE §42) se lo stream SSE non e' disponibile:
      // finche' l'import non e' in uno stato terminale, ricontrolla.
      const status = query.state.data?.status;
      if (!status || status === "completed" || status === "failed" || status === "cancelled") return false;
      return 3000;
    },
  });
}

export interface ImportProgressEvent {
  event: string;
  stage?: string;
  progress?: number;
  message?: string;
  transactions_found?: number;
  transactions_imported?: number;
}

/**
 * Legge lo stream SSE di `GET /imports/{id}/events` con `fetch` +
 * `ReadableStream` (non `EventSource`, che non può mandare l'header
 * Authorization — vedi `backend/app/api/v1/imports.py:422`).
 */
export async function streamImportEvents(
  importId: string,
  onEvent: (event: ImportProgressEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(`${api.base}/imports/${importId}/events`, {
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
