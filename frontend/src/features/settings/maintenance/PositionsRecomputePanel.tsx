import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { JobRunStatus } from "../../../components/ui/JobRunStatus";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import { formatDateTime } from "../../../lib/format";
import type { PositionsRecomputeDetails } from "../../../types/api";
import { PositionChangesTable } from "./PositionChangesTable";
import { usePositionsRecomputePreview, usePositionsRecomputeStatus, useTriggerPositionsRecompute } from "./api";

/** Ricalcolo manuale delle posizioni dai movimenti. `positions` e' un valore
 * salvato che si aggiorna solo quando un suo movimento cambia: dopo una
 * correzione al calcolo i valori gia' salvati restano quelli vecchi. Tre
 * momenti: anteprima (nessuna scrittura), avvio del job, resoconto
 * dell'ultima esecuzione (persistito: sopravvive a un refresh pagina). */
export function PositionsRecomputePanel() {
  const { t } = useTranslation("settings");
  const queryClient = useQueryClient();
  const [waitingFor, setWaitingFor] = useState<{ previousStartedAt: string | null } | null>(null);
  const status = usePositionsRecomputeStatus(waitingFor !== null);
  const preview = usePositionsRecomputePreview();
  const trigger = useTriggerPositionsRecompute();
  const [error, setError] = useState<string | null>(null);

  const run = status.data ?? null;
  const running = run?.status === "running" || waitingFor !== null;
  const details = (run?.details ?? null) as PositionsRecomputeDetails | null;

  // Quando il job finisce, gli analytics e le posizioni mostrate altrove
  // nell'app sono cambiati: vanno ricaricati.
  const previousStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (previousStatus.current === "running" && run?.status !== "running") {
      void queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    }
    previousStatus.current = run?.status;
  }, [run?.status, queryClient]);

  // L'attesa finisce quando compare un'esecuzione nuova e conclusa, o dopo 60s
  // (worker fermo: meglio smettere di far girare il pulsante che restare
  // appesi per sempre).
  useEffect(() => {
    if (waitingFor === null) return undefined;
    if (run && run.started_at !== waitingFor.previousStartedAt && run.status !== "running") {
      setWaitingFor(null);
      return undefined;
    }
    const timeout = window.setTimeout(() => setWaitingFor(null), 60000);
    return () => window.clearTimeout(timeout);
  }, [waitingFor, run]);

  const onPreview = async () => {
    setError(null);
    const result = await preview.refetch();
    if (result.isError) setError(friendlyErrorMessage(result.error, t("items.maintenance.positions.previewError")));
  };

  const onRun = async () => {
    setError(null);
    try {
      await trigger.mutateAsync();
      setWaitingFor({ previousStartedAt: run?.started_at ?? null });
    } catch (failure) {
      setError(friendlyErrorMessage(failure, t("items.maintenance.positions.runError")));
    }
  };

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="text-base font-semibold text-text">{t("items.maintenance.positions.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("items.maintenance.positions.description")}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => void onPreview()} loading={preview.isFetching} disabled={running}>
          {t("items.maintenance.positions.preview")}
        </Button>
        <Button onClick={() => void onRun()} loading={trigger.isPending || running}>
          {running ? t("items.maintenance.positions.running") : t("items.maintenance.positions.run")}
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {preview.data && (
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">{t("items.maintenance.positions.previewTitle")}</h3>
          <p className="text-sm text-text-muted">
            {t("items.maintenance.positions.summary", { changed: preview.data.changed, checked: preview.data.checked })}
          </p>
          {preview.data.changes.length > 0 && <PositionChangesTable changes={preview.data.changes} />}
        </section>
      )}

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-text">{t("items.maintenance.positions.lastRun")}</h3>
        <JobRunStatus run={run} />
        {details && (
          <>
            {details.changes.length > 0 && <PositionChangesTable changes={details.changes} />}
            {details.truncated && (
              <p className="text-xs text-text-muted">
                {t("items.maintenance.positions.truncated", { shown: details.changes.length })}
              </p>
            )}
            {details.changed === 0 && details.previous_changes && (
              <div className="mt-2 flex flex-col gap-2">
                <h4 className="text-sm font-medium text-text">
                  {t("items.maintenance.positions.previousChanges", { date: formatDateTime(details.previous_changes.at) })}
                </h4>
                <p className="text-sm text-text-muted">
                  {t("items.maintenance.positions.summary", {
                    changed: details.previous_changes.changed,
                    checked: details.previous_changes.checked,
                  })}
                </p>
                <PositionChangesTable changes={details.previous_changes.changes} />
              </div>
            )}
          </>
        )}
      </section>
    </Card>
  );
}
