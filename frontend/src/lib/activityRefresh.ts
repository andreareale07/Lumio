import type { QueryClient } from "@tanstack/react-query";

// Subito dopo un'azione (importare, riclassificare, rilanciare l'AI...) il
// worker puo' non aver ancora registrato il job come "in corso": una sola
// rilettura immediata lo mancherebbe, e a riposo l'indicatore globale scorre
// solo ogni 30s. Poche riletture ravvicinate coprono la partenza del job senza
// tenere un polling veloce acceso per sempre.
const REFRESH_DELAYS_MS = [0, 2000, 5000, 10000];

export function scheduleActivityRefresh(queryClient: QueryClient): void {
  for (const delay of REFRESH_DELAYS_MS) {
    window.setTimeout(() => {
      void queryClient.invalidateQueries({ queryKey: ["activity"] });
    }, delay);
  }
}
