import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import type { JobRun } from "../../types/api";
import { reclassificationStatusKey, streamReclassificationEvents } from "./api";

export interface ReclassificationProgress {
  processed: number;
  total: number;
  detail?: string;
}

/** Stato "vivo" della riclassificazione, valido anche dopo un ricaricamento
 * della pagina: lo stato arriva dal server (non da un flag locale) e, se il
 * job sta girando, ci si riaggancia al suo stream di eventi per riavere
 * avanzamento x/N (lo stream rigioca gli eventi passati). Prima il progresso
 * esisteva solo nella sessione che aveva premuto il pulsante: ricaricando
 * restava un "In corso" generico senza numeri e senza dire dove seguirlo. */
export function useReclassificationLive() {
  const queryClient = useQueryClient();
  const [waiting, setWaiting] = useState<{ previousStartedAt: string | null } | null>(null);
  const [progress, setProgress] = useState<ReclassificationProgress | null>(null);

  const status = useQuery({
    queryKey: reclassificationStatusKey,
    queryFn: () => api.get<JobRun | null>("/classification/reclassify/status"),
    // Subito dopo il clic il worker puo' non aver ancora registrato 'running':
    // senza il polling forzato (`waiting`) lo stato non si aggiornerebbe mai.
    refetchInterval: (query) => (waiting !== null || query.state.data?.status === "running" ? 3000 : false),
  });

  const run = status.data ?? null;
  const serverRunning = run?.status === "running";
  const running = serverRunning || waiting !== null;

  // L'attesa finisce quando compare un'esecuzione nuova e conclusa, o dopo 60s
  // (worker fermo: meglio smettere di far girare il pulsante).
  useEffect(() => {
    if (waiting === null) return undefined;
    if (run && run.started_at !== waiting.previousStartedAt && run.status !== "running") {
      setWaiting(null);
      void queryClient.invalidateQueries();
      return undefined;
    }
    const timeout = window.setTimeout(() => setWaiting(null), 60000);
    return () => window.clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- queryClient e' stabile
  }, [waiting, run]);

  useEffect(() => {
    if (!serverRunning) return undefined;
    const controller = new AbortController();
    streamReclassificationEvents((event) => {
      if (event.event === "job.progress" || event.event === "job.completed") {
        setProgress({ processed: event.processed ?? 0, total: event.total ?? 0, detail: event.detail });
      }
      if (event.event === "job.completed" || event.event === "job.failed" || event.event === "job.cancelled") {
        setProgress(null);
        void status.refetch();
        // Categorie e analytics sono cambiate: tutto cio' che e' a schermo va riletto.
        void queryClient.invalidateQueries();
      }
    }, controller.signal).catch(() => {
      // Nessun fallback: il polling dello stato mostra comunque l'esito.
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al cambio di 'in esecuzione'
  }, [serverRunning]);

  return {
    run,
    running,
    progress,
    markStarted: () => setWaiting({ previousStartedAt: run?.started_at ?? null }),
  };
}

export type ReclassificationLive = ReturnType<typeof useReclassificationLive>;
