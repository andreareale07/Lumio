import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { streamImportEvents, type ImportProgressEvent } from "./api";
import { importStageLabel } from "./labels";

/** Indicatore di progresso live per una riga della lista Import — sostituto
 * di un badge statico "In elaborazione" per import in `queued`/`processing`/
 * `parsing`. Riusa lo stesso stream SSE già consumato da `ImportWizard.tsx`
 * durante l'upload: il backend fa replay dell'intero stream da Redis (mai
 * solo i nuovi eventi), quindi funziona anche se l'utente ha chiuso il
 * wizard, navigato altrove, e torna sulla lista in un momento successivo —
 * non solo durante la sessione di upload corrente. */
export function ImportRowProgress({ importId, onSettled }: { importId: string; onSettled: () => void }) {
  const { t } = useTranslation("imports");
  const [stage, setStage] = useState<"queued" | "preparazione" | "estrazione" | "salvataggio">("queued");

  useEffect(() => {
    const controller = new AbortController();

    const handleEvent = (event: ImportProgressEvent) => {
      if (event.event === "job.created" || event.event === "job.started") {
        setStage("preparazione");
      }
      if (event.event === "job.progress" && event.stage === "parsing") {
        setStage((event.progress ?? 0) >= 60 ? "salvataggio" : "estrazione");
      }
      if (event.event === "job.completed" || event.event === "job.failed" || event.event === "job.cancelled") {
        onSettled();
        controller.abort();
      }
    };

    streamImportEvents(importId, handleEvent, controller.signal).catch(() => {
      // Nessun fallback qui: la lista resta comunque corretta al prossimo
      // caricamento/refresh manuale, il badge di stato statico non e' perso.
    });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importId]);

  return (
    <span className="flex items-center gap-1.5 text-sm text-text-muted">
      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      {importStageLabel(t, stage)}
    </span>
  );
}
