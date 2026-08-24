import { useEffect, useState } from "react";
import { Sparkles, Wand2 } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { JobRunStatus } from "../../components/ui/JobRunStatus";
import { Select } from "../../components/ui/Select";
import { Skeleton } from "../../components/ui/Skeleton";
import { useEtaEstimate, type EtaLabelStrings } from "../../lib/eta";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { RECLASSIFICATION_SCOPES, type ReclassificationScope } from "../../types/api";
import { useCategoryLabel } from "../categories/utils";
import { useCategories } from "../categories/api";
import {
  streamReclassificationEvents,
  useReclassificationPreview,
  useReclassificationStatus,
  useTriggerReclassification,
} from "./api";

/**
 * Riapplica le regole (e opzionalmente l'AI) a transazioni GIA' importate —
 * serve dopo aver creato/modificato una regola, per classificare anche lo
 * storico invece che solo i movimenti futuri. Il backend (`POST
 * /classification/reclassify`, milestone reclassification job) esisteva già
 * ma non aveva un punto d'ingresso in UI: mai una scrittura silenziosa,
 * l'anteprima mostra sempre l'impatto prima del bottone che lancia il job
 * vero. Una `Classification(method IN ('user','manual'))` non viene mai
 * toccata (vedi backend/app/worker/jobs/reclassification_job.py) — motivo
 * per cui "Tutte tranne quelle corrette a mano" è comunque sicuro da offrire.
 */
export function ReclassificationPanel() {
  const { t } = useTranslation("settings");
  const categoryLabel = useCategoryLabel();
  const { data: categories } = useCategories();
  const [scope, setScope] = useState<ReclassificationScope>("uncategorized");
  const [runAi, setRunAi] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ processed: number; total: number; detail?: string } | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);

  const preview = useReclassificationPreview(scope);
  const status = useReclassificationStatus();
  const trigger = useTriggerReclassification();

  const etaLabels: EtaLabelStrings = {
    lessThanAMinute: () => t("common:eta.lessThanAMinute"),
    minutes: (count) => t("common:eta.minutes", { count }),
    hours: (hours, minutes) =>
      minutes > 0 ? t("common:eta.hoursMinutes", { hours, minutes }) : t("common:eta.hours", { hours }),
  };
  const eta = useEtaEstimate(progress?.processed ?? null, progress?.total ?? null, startedAt, etaLabels);

  useEffect(() => {
    if (!running) return undefined;
    const controller = new AbortController();

    streamReclassificationEvents((event) => {
      if (event.event === "job.progress" || event.event === "job.completed") {
        setProgress({ processed: event.processed ?? 0, total: event.total ?? 0, detail: event.detail });
      }
      if (event.event === "job.completed" || event.event === "job.failed" || event.event === "job.cancelled") {
        setRunning(false);
        setProgress(null);
        void status.refetch();
        void preview.refetch();
      }
    }, controller.signal).catch(() => {
      // Nessun fallback qui: JobRunStatus mostra comunque lo stato terminale
      // persistito al prossimo refresh/refetch manuale.
      setRunning(false);
    });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo su running
  }, [running]);

  const onApply = async () => {
    setError(null);
    try {
      await trigger.mutateAsync({ scope, run_ai: runAi });
      setStartedAt(new Date().toISOString());
      setProgress({ processed: 0, total: preview.data?.total_candidates ?? 0 });
      setRunning(true);
    } catch (err) {
      setError(friendlyErrorMessage(err, t("items.rules.page.reclassification.error")));
    }
  };

  return (
    <Card className="flex flex-col gap-3">
      <div>
        <p className="font-medium text-text">{t("items.rules.page.reclassification.title")}</p>
        <p className="text-sm text-text-muted">{t("items.rules.page.reclassification.description")}</p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label={t("items.rules.page.reclassification.scopeLabel")}
          value={scope}
          onChange={(e) => setScope(e.target.value as ReclassificationScope)}
          disabled={running}
        >
          {RECLASSIFICATION_SCOPES.map((s) => (
            <option key={s} value={s}>
              {t(`items.rules.page.reclassification.scopes.${s}`)}
            </option>
          ))}
        </Select>
        <label className="flex items-end gap-2 pb-2.5 text-sm text-text-muted">
          <input
            type="checkbox"
            checked={runAi}
            onChange={(e) => setRunAi(e.target.checked)}
            disabled={running}
            className="h-4 w-4 rounded border-border"
          />
          {t("items.rules.page.reclassification.useAiCheckbox")}
        </label>
      </div>

      {preview.isLoading && <Skeleton className="h-10 w-full" />}
      {preview.data && !running && (
        <div className="rounded-lg border border-border bg-surface-hover p-3 text-sm">
          {preview.data.total_candidates === 0 ? (
            <p className="text-text-muted">{t("items.rules.page.reclassification.noneInScope")}</p>
          ) : (
            <>
              <p className="text-text">
                <Trans
                  t={t}
                  i18nKey="items.rules.page.reclassification.wouldChange"
                  values={{ count: preview.data.would_change, total: preview.data.total_candidates }}
                  components={{ strong: <strong /> }}
                />
              </p>
              {preview.data.breakdown.length > 0 && (
                <ul className="mt-1.5 flex flex-col gap-0.5 text-text-muted">
                  {preview.data.breakdown.map((b) => (
                    <li key={b.category_id}>
                      {b.count}× → {categoryLabel(categories, b.category_id) || b.category_name}
                      {b.examples.length > 0 &&
                        t("items.rules.page.reclassification.breakdownExample", { example: b.examples[0] })}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}

      {running && progress && (
        <p className="flex items-center gap-1.5 text-sm text-text-muted">
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          {t("items.rules.page.reclassification.inProgress", { processed: progress.processed, total: progress.total })}
          {progress.detail && ` — ${progress.detail}`}
          {eta && ` — ${eta.label}`}
        </p>
      )}

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <Button
        size="sm"
        className="self-start"
        loading={trigger.isPending || running}
        disabled={!preview.data || preview.data.total_candidates === 0}
        onClick={() => void onApply()}
      >
        <Wand2 className="h-4 w-4" /> {t("items.rules.page.reclassification.applyNow")}
      </Button>

      {!running && <JobRunStatus run={status.data} />}
    </Card>
  );
}
