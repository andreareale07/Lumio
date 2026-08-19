import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, getAccessToken } from "../../lib/apiClient";
import type { ImportRecord, ImportUploadResponse, MappingConfig } from "../../types/api";

export interface DuplicateReviewCandidate {
  id: string;
  transaction_date: string;
  description_raw: string;
  description_normalized: string | null;
  amount: string;
  currency: string;
  transaction_type: string;
  balance_after: string | null;
}

export interface DuplicateReviewItem {
  id: string;
  import_id: string;
  financial_account_id: string;
  row_index: number;
  transaction_date: string;
  description_raw: string;
  description_normalized: string | null;
  amount: string;
  currency: string;
  transaction_type: string;
  balance_after: string | null;
  status: "pending" | "confirmed_new" | "confirmed_duplicate";
  auto_resolved: boolean;
  decided_at: string | null;
  created_at: string;
  candidate: DuplicateReviewCandidate | null;
}

export interface DuplicateReviewSummary {
  pending: number;
  confirmed_new: number;
  confirmed_duplicate: number;
}

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

export function useDeleteImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (importId: string) => api.delete<{ deleted_transactions_count: number }>(`/imports/${importId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: importsKey }),
  });
}

/** Conteggio LIVE delle transazioni collegate — usato dal dialog di
 * conferma eliminazione per mostrare l'impatto reale (mai il contatore
 * `transactions_imported`, che non riflette eliminazioni singole
 * successive delle stesse transazioni). */
export function useImportTransactionsCount(importId: string | null) {
  return useQuery({
    queryKey: ["imports", importId, "transactions-count"],
    queryFn: () => api.get<{ transactions_count: number }>(`/imports/${importId}/transactions-count`),
    enabled: !!importId,
  });
}

export interface ImportFileContent {
  columns: string[];
  rows: string[][];
  truncated: boolean;
  total_rows: number;
}

export function useImportFileContent(importId: string | null) {
  return useQuery({
    queryKey: ["imports", importId, "file-content"],
    queryFn: () => api.get<ImportFileContent>(`/imports/${importId}/file-content`),
    enabled: !!importId,
  });
}

/**
 * Scarica i byte grezzi del file originale come Blob, per un `<embed>` PDF
 * lato client — stesso motivo di `streamImportEvents`: un `<embed>`/`<iframe>`
 * non manda l'header Authorization, quindi va fetchato qui e passato come
 * `blob:` URL (mai un token in query string, finirebbe nei log).
 */
export async function fetchImportFileBlob(importId: string): Promise<Blob> {
  const token = getAccessToken();
  const response = await fetch(`${api.base}/imports/${importId}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (!response.ok) {
    throw new ApiError(response.status, "Impossibile scaricare il file originale", null);
  }
  return response.blob();
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
      // "ready_for_review" ferma il polling di stato del JOB (l'esecuzione
      // asincrona e' comunque terminata, resta solo la decisione
      // dell'utente sui candidati ambigui) — vedi useImportReviewSummary/
      // useImportReviewItems per lo stato della revisione stessa.
      if (
        !status ||
        status === "completed" ||
        status === "failed" ||
        status === "cancelled" ||
        status === "ready_for_review"
      )
        return false;
      return 3000;
    },
  });
}

/** SPEC §15/§31: elenco dei candidati ambigui (default solo i 'pending') con
 * il record esistente a confronto, per la UI di revisione duplicati. */
export function useImportReviewItems(importId: string | null, status: string = "pending") {
  return useQuery({
    queryKey: ["imports", importId, "review-items", status],
    queryFn: () =>
      api.get<DuplicateReviewItem[]>(`/imports/${importId}/review-items?status=${status}`),
    enabled: !!importId,
  });
}

export function useImportReviewSummary(importId: string | null) {
  return useQuery({
    queryKey: ["imports", importId, "review-summary"],
    queryFn: () => api.get<DuplicateReviewSummary>(`/imports/${importId}/review-summary`),
    enabled: !!importId,
  });
}

export function useDecideImportReviewItem(importId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, decision }: { itemId: string; decision: "keep_new" | "mark_duplicate" }) =>
      api.post<DuplicateReviewItem>(`/imports/${importId}/review-items/${itemId}/decision`, { decision }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["imports", importId, "review-items"] });
      queryClient.invalidateQueries({ queryKey: ["imports", importId, "review-summary"] });
      queryClient.invalidateQueries({ queryKey: ["imports", importId] });
      queryClient.invalidateQueries({ queryKey: importsKey });
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

/** Esportata anche per altre feature con un proprio stream SSE (es.
 * activity, reclassificazione): stessa ragione (fetch()+ReadableStream, non
 * EventSource) documentata sopra, nessun motivo di duplicare il parsing. */
export async function streamSse(
  path: string,
  onEvent: (event: ImportProgressEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(`${api.base}${path}`, {
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
  return streamSse(`/imports/${importId}/events`, onEvent, signal);
}

export interface AiClassificationProgressEvent {
  event: string;
  processed?: number;
  total?: number;
  message?: string;
}

/**
 * Stream SSE del namespace 'ai_classification' (job disaccoppiato dal job
 * di import — vedi backend/app/worker/jobs/ai_classification_job.py). Stesso
 * meccanismo di `streamImportEvents`, endpoint separato.
 */
export async function streamAiClassificationEvents(
  importId: string,
  onEvent: (event: AiClassificationProgressEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  return streamSse(`/imports/${importId}/ai-classification-events`, onEvent, signal);
}
