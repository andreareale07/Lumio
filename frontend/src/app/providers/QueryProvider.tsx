import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { scheduleActivityRefresh } from "../../lib/activityRefresh";
import { ApiError } from "../../lib/apiClient";

const queryClient: QueryClient = new QueryClient({
  // Qualunque azione riuscita puo' aver avviato un job: l'indicatore delle
  // elaborazioni (barra superiore) deve accorgersene subito, non dopo 30s.
  mutationCache: new MutationCache({ onSuccess: () => scheduleActivityRefresh(queryClient) }),
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Non ritentare mai su errori 4xx (client error): non e' un
        // problema transitorio, ritentare non cambierebbe l'esito.
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return failureCount < 2;
      },
      staleTime: 30_000,
    },
  },
});

export function QueryProvider({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
