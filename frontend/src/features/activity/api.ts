import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import { streamSse } from "../imports/api";

export interface ActivityItem {
  kind: string;
  label: string;
  label_key: string | null;
  status: string;
  events_url: string | null;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
  processed: number | null;
  total: number | null;
}

interface ActivityListResponse {
  items: ActivityItem[];
}

export const activityKey = ["activity"] as const;

/** Polling semplice (non SSE) per la lista stessa: l'elenco di QUALI
 * operazioni esistono cambia raramente rispetto alla frequenza degli
 * eventi di progresso di ognuna, che invece si guardano via SSE per-item
 * (vedi useActivityItemProgress) — stesso rapporto polling/SSE già usato
 * da useImport + streamImportEvents. */
export function useActivity() {
  return useQuery({
    queryKey: activityKey,
    queryFn: () => api.get<ActivityListResponse>("/activity").then((r) => r.items),
    refetchInterval: 5000,
  });
}

export interface ActivityProgressEvent {
  event: string;
  processed?: number;
  total?: number;
  detail?: string;
  message?: string;
  stage?: string;
}

/** Stream SSE generico per una riga del cruscotto Attività: ogni kind ha
 * il proprio endpoint /events già esistente (import, ai_classification,
 * reclassification, google_sheets_export — vedi activity_service.py), qui
 * letto con lo stesso streamSse riusato da imports/api.ts. I job schedulati
 * senza `events_url` restano fermi allo stato persistito (nessuno stream). */
export async function streamActivityItemEvents(
  eventsUrl: string,
  onEvent: (event: ActivityProgressEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  return streamSse(eventsUrl, onEvent, signal);
}
