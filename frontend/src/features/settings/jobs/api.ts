import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../../lib/apiClient";
import type { Job } from "../../../types/api";

export const jobsKey = ["jobs"] as const;

export function useJobs() {
  return useQuery({
    queryKey: jobsKey,
    queryFn: () => api.get<Job[]>("/jobs"),
  });
}

/** Un solo endpoint di scrittura, gia' esistente (`/system-settings/{key}`,
 * vedi ImpostazioniPage Job): sia le soglie editabili sia il flag
 * enabled/disabled dei job schedulati sono righe in `system_settings`, non
 * serve un endpoint dedicato per il toggle. */
export function useUpdateSystemSetting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      api.patch(`/system-settings/${encodeURIComponent(key)}`, { value }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: jobsKey }),
  });
}
