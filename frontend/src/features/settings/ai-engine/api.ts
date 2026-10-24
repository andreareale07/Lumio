import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../../lib/apiClient";
import type { AIEngineStatus, AIEventSeverity, AIRunEventList, JobRun } from "../../../types/api";
import { reclassificationStatusKey } from "../../rules/api";

export const aiEngineStatusKey = ["ai-engine", "status"] as const;
const aiEngineEventsKey = ["ai-engine", "events"] as const;

/** Stato del motore AI: profilo attivo, righe ancora da classificare, ultimi
 * import con il loro stato AI. Polling ogni 3s finche' qualche import e' in
 * coda o in esecuzione, cosi' il progresso si vede senza ricaricare. */
export function useAIEngineStatus(forcePoll = false) {
  return useQuery({
    queryKey: aiEngineStatusKey,
    queryFn: () => api.get<AIEngineStatus>("/ai-engine/status"),
    refetchInterval: (query) =>
      forcePoll || query.state.data?.recent_imports.some((i) => i.ai_status === "pending" || i.ai_status === "running")
        ? 3000
        : false,
  });
}

export function useAIEngineEvents(severity: AIEventSeverity | null, limit: number, forcePoll = false) {
  return useQuery({
    queryKey: [...aiEngineEventsKey, severity ?? "all", limit] as const,
    // Dopo un rilancio il job puo' finire prima che lo stato risulti 'running':
    // si rilegge comunque per qualche secondo, altrimenti il registro resta fermo.
    refetchInterval: forcePoll ? 3000 : false,
    queryFn: () => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (severity) params.set("severity", severity);
      return api.get<AIRunEventList>(`/ai-engine/events?${params.toString()}`);
    },
    // Tiene visibile la lista mentre "Carica altri" scarica la pagina piu' lunga.
    placeholderData: (previous) => previous,
  });
}

export function useRetryImportAI() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (importId: string) =>
      api.post<{ ai_status: string | null; ai_total: number }>(`/ai-engine/imports/${importId}/retry`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiEngineStatusKey });
      void queryClient.invalidateQueries({ queryKey: aiEngineEventsKey });
    },
  });
}

/** Da chiamare quando una riclassificazione (job separato, vedi
 * `features/rules/api.ts`) termina: stato e registro eventi sono cambiati. */
export function useInvalidateAIEngine() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: aiEngineStatusKey });
    void queryClient.invalidateQueries({ queryKey: aiEngineEventsKey });
  };
}

/** Stato dell'ultima riclassificazione (stesso job e stessa cache della pagina
 * Regole), con polling mentre e' in corso o appena accodata (`forcePoll`):
 * subito dopo il click il worker puo' non aver ancora registrato 'running'. */
export function useReclassificationRunStatus(forcePoll: boolean) {
  return useQuery({
    queryKey: reclassificationStatusKey,
    queryFn: () => api.get<JobRun | null>("/classification/reclassify/status"),
    refetchInterval: (query) => (forcePoll || query.state.data?.status === "running" ? 2000 : false),
  });
}
