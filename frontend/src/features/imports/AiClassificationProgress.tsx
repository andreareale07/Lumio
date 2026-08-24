import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useEtaEstimate, type EtaLabelStrings } from "../../lib/eta";
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
  startedAt,
  onSettled,
}: {
  importId: string;
  total: number;
  /** Istante da cui stimare la velocita' "media da inizio" (vedi
   * `useEtaEstimate`) — l'import stesso e' gia' 'completed' quando questo
   * componente e' montato, quindi `completed_at` dell'import e' il punto di
   * partenza piu' vicino che abbiamo alla classificazione AI vera e propria
   * (nessun timestamp dedicato persistito per quella fase). */
  startedAt: string | null;
  onSettled: () => void;
}) {
  const { t } = useTranslation("imports");
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

  const etaLabels: EtaLabelStrings = {
    lessThanAMinute: () => t("common:eta.lessThanAMinute"),
    minutes: (count) => t("common:eta.minutes", { count }),
    hours: (hours, minutes) =>
      minutes > 0 ? t("common:eta.hoursMinutes", { hours, minutes }) : t("common:eta.hours", { hours }),
  };
  const eta = useEtaEstimate(processed, total, startedAt, etaLabels);

  return (
    <span className="flex items-center gap-1.5 text-sm text-text-muted">
      <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
      {t("aiProgress.label", { processed, total })}
      {eta && ` — ${eta.label}`}
    </span>
  );
}
