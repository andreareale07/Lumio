import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../../lib/apiClient";
import type { Currency, Workspace } from "../../../types/api";

export const currenciesKey = ["currencies"] as const;
export const workspaceKey = ["workspace"] as const;

/** Elenco valute (di sistema + eventuali custom del workspace) — cambia
 * pochissimo, `staleTime` lungo evita di ririchiederlo ad ogni form aperto. */
export function useCurrencies() {
  return useQuery({
    queryKey: currenciesKey,
    queryFn: () => api.get<Currency[]>("/currencies"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useWorkspace() {
  return useQuery({
    queryKey: workspaceKey,
    queryFn: () => api.get<Workspace>("/workspace"),
  });
}

export function useUpdateWorkspaceCurrency() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (base_currency: string) => api.patch<Workspace>("/workspace", { base_currency }),
    onSuccess: () => {
      // Invalida TUTTO cio' che dipende dalla valuta risolta (analytics,
      // portfolio) — cambiare base_currency ricalcola ogni totale aggregato.
      queryClient.invalidateQueries({ queryKey: workspaceKey });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    },
  });
}
