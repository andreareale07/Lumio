import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

import { streamAiClassificationEvents, type AiClassificationProgressEvent } from "./api";

/** Indicatore live "x/N" per la classificazione AI disaccoppiata dal job di
 * import (rework UX/design) — stesso pattern SSE di `ImportRowProgress.tsx`,
 * namespace/endpoint diversi. Mostrato solo per import con
 * `ai_classification_status` 'pending'/'running' (vedi `ImportsPage.tsx`):
 * l'import stesso è già 'completed', questo indicatore riguarda solo il
 * lavoro di background successivo. */
export function AiClassificationProgress({
  importId,
  total,
  onSettled,
}: {
  importId: string;
  total: number;
  onSettled: () => void;
}) {
  const [processed, setProcessed] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    const handleEvent = (event: AiClassificationProgressEvent) => {
      if (event.event === "job.progress" || event.event === "job.completed") {
        setProcessed(event.processed ?? 0);
      }
      if (event.event === "job.completed" || event.event === "job.failed" || event.event === "job.cancelled") {
        onSettled();
        controller.abort();
      }
    };

    streamAiClassificationEvents(importId, handleEvent, controller.signal).catch(() => {
      // Nessun fallback qui: al prossimo refresh manuale della lista lo
      // stato terminale arriva comunque da ImportOut.ai_classification_status.
    });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importId]);

  return (
    <span className="flex items-center gap-1.5 text-sm text-text-muted">
      <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
      Classificazione AI: {processed}/{total}
    </span>
  );
}
