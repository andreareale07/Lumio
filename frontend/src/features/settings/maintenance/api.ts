import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../../lib/apiClient";
import type { JobRun, PositionsRecomputePreview } from "../../../types/api";

export const positionsRecomputeStatusKey = ["maintenance", "positions-recompute", "status"] as const;

/** Anteprima sincrona (nessuna scrittura): parte solo su richiesta esplicita
 * (`enabled: false` + `refetch()`), mai da sola al caricamento della pagina —
 * ricalcola davvero tutte le posizioni e scarta il risultato. */
export function usePositionsRecomputePreview() {
  return useQuery({
    queryKey: ["maintenance", "positions-recompute", "preview"] as const,
    queryFn: () => api.get<PositionsRecomputePreview>("/maintenance/positions-recompute/preview"),
    enabled: false,
    gcTime: 0,
  });
}

/** Stato dell'ultima esecuzione, con polling ogni 2s finche' e' 'running' o
 * mentre si attende che una nuova esecuzione appena accodata parta (`forcePoll`):
 * subito dopo il click il worker puo' non aver ancora registrato 'running', e
 * senza questo il polling non partirebbe mai. */
export function usePositionsRecomputeStatus(forcePoll = false) {
  return useQuery({
    queryKey: positionsRecomputeStatusKey,
    queryFn: () => api.get<JobRun | null>("/maintenance/positions-recompute/status"),
    refetchInterval: (query) => (forcePoll || query.state.data?.status === "running" ? 2000 : false),
  });
}

export function useTriggerPositionsRecompute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ job_id: string }>("/maintenance/positions-recompute"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: positionsRecomputeStatusKey }),
  });
}
