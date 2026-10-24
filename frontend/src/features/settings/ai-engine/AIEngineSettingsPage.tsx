import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { PAGE_WIDTH_WIDE } from "../../../components/layout/pageWidths";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { ErrorState } from "../../../components/ui/ErrorState";
import { JobRunStatus } from "../../../components/ui/JobRunStatus";
import { Select } from "../../../components/ui/Select";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import { formatDateTime } from "../../../lib/format";
import type { AIEngineImport, AIEventSeverity } from "../../../types/api";
import { useTriggerReclassification } from "../../rules/api";
import { CancelActivityButton } from "../../activity/CancelActivityButton";
import {
  useAIEngineEvents,
  useAIEngineStatus,
  useInvalidateAIEngine,
  useReclassificationRunStatus,
  useRetryImportAI,
} from "./api";
import { describeEvent } from "./describeEvent";

const EVENTS_PAGE_SIZE = 25;

const STATUS_TONE: Record<NonNullable<AIEngineImport["ai_status"]>, "primary" | "success" | "danger" | "neutral"> = {
  pending: "primary",
  running: "primary",
  completed: "success",
  failed: "danger",
  skipped: "neutral",
  cancelled: "neutral",
};

const SEVERITY_TONE: Record<AIEventSeverity, "danger" | "warning" | "neutral"> = {
  error: "danger",
  warning: "warning",
  info: "neutral",
};

/** Impostazioni > Motore AI: stato del motore di classificazione, errori e
 * malfunzionamenti (prima visibili solo nel log del worker) e rilancio
 * manuale. L'AI parte solo dopo un import completato o da "Riclassifica":
 * qui si vede perche' non e' partita e si puo' rilanciare a mano. */
export function AIEngineSettingsPage() {
  const { t } = useTranslation("settings");
  const [settling, setSettling] = useState(false);
  const [waiting, setWaiting] = useState<{ previousStartedAt: string | null } | null>(null);
  const status = useAIEngineStatus(settling);
  const reclassStatus = useReclassificationRunStatus(waiting !== null);
  const [severity, setSeverity] = useState<AIEventSeverity | null>(null);
  const [eventsLimit, setEventsLimit] = useState(EVENTS_PAGE_SIZE);
  const retry = useRetryImportAI();
  const trigger = useTriggerReclassification();
  const invalidate = useInvalidateAIEngine();
  const [error, setError] = useState<string | null>(null);

  const run = reclassStatus.data ?? null;
  const reclassRunning = run?.status === "running" || waiting !== null;

  // Qualcosa sta girando (import in coda o in corso, riclassificazione): il
  // registro si rilegge finche' dura, e per qualche secondo dopo la fine, perche'
  // il job scrive l'ultimo evento DOPO aver cambiato lo stato.
  const anyActive =
    (status.data?.recent_imports ?? []).some((i) => i.ai_status === "pending" || i.ai_status === "running") ||
    run?.status === "running";
  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && !anyActive) settleForAWhile();
    wasActive.current = anyActive;
  }, [anyActive]);
  const events = useAIEngineEvents(severity, eventsLimit, settling || anyActive);

  // L'attesa finisce quando compare un'esecuzione nuova e conclusa, o dopo 60s
  // (worker fermo: meglio smettere di far girare il pulsante).
  useEffect(() => {
    if (waiting === null) return undefined;
    if (run && run.started_at !== waiting.previousStartedAt && run.status !== "running") {
      setWaiting(null);
      invalidate();
      settleForAWhile();
      return undefined;
    }
    const timeout = window.setTimeout(() => setWaiting(null), 60000);
    return () => window.clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `invalidate` cambia identita' ad ogni render
  }, [waiting, run]);

  const onClassify = async () => {
    setError(null);
    try {
      await trigger.mutateAsync({ scope: "uncategorized", run_ai: true });
      setWaiting({ previousStartedAt: run?.started_at ?? null });
    } catch (failure) {
      setError(friendlyErrorMessage(failure, t("items.aiEngine.classify.error")));
    }
  };

  // Per qualche secondo dopo un rilancio stato e registro si rileggono da soli.
  const settleForAWhile = () => {
    setSettling(true);
    window.setTimeout(() => setSettling(false), 15000);
  };

  const onRetry = async (importId: string) => {
    setError(null);
    try {
      await retry.mutateAsync(importId);
      settleForAWhile();
    } catch (failure) {
      setError(friendlyErrorMessage(failure, t("items.aiEngine.imports.retryError")));
    }
  };

  const data = status.data;
  const hasProfile = data?.active_profile != null;

  return (
    <div className={PAGE_WIDTH_WIDE}>
      <div>
        <h1 className="text-lg font-semibold text-text">{t("items.aiEngine.label")}</h1>
        <p className="text-sm text-text-muted">{t("items.aiEngine.pageDescription")}</p>
      </div>

      {status.isLoading && <SkeletonRows rows={3} />}
      {status.isError && (
        <ErrorState message={t("items.aiEngine.loadError")} onRetry={() => void status.refetch()} />
      )}

      {data && (
        <>
          <Card className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-semibold text-text">{t("items.aiEngine.state.title")}</h2>
              <Link to="/settings/ai" className="text-sm text-primary hover:underline">
                {t("items.aiEngine.state.manageProfiles")}
              </Link>
            </div>
            {data.active_profile ? (
              <p className="text-sm text-text">
                {t("items.aiEngine.state.activeProfile", {
                  name: data.active_profile.name,
                  provider: data.active_profile.provider,
                  model: data.active_profile.model ?? "—",
                })}
              </p>
            ) : (
              <p role="status" className="text-sm text-warning">
                {t("items.aiEngine.state.noProfile")}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Badge tone={data.uncategorized_eligible > 0 ? "warning" : "success"}>
                {t("items.aiEngine.state.uncategorized", { count: data.uncategorized_eligible })}
              </Badge>
              <Badge tone={data.errors_last_24h > 0 ? "danger" : "success"}>
                {t("items.aiEngine.state.errors24h", { count: data.errors_last_24h })}
              </Badge>
            </div>
            {data.last_error_at && (
              <p className="text-xs text-text-muted">
                {t("items.aiEngine.state.lastError", { date: formatDateTime(data.last_error_at) })}
              </p>
            )}
          </Card>

          <Card className="flex flex-col gap-3">
            <div>
              <h2 className="text-base font-semibold text-text">{t("items.aiEngine.classify.title")}</h2>
              <p className="mt-1 text-sm text-text-muted">{t("items.aiEngine.classify.description")}</p>
            </div>
            <div>
              <Button
                onClick={() => void onClassify()}
                loading={trigger.isPending || reclassRunning}
                disabled={!hasProfile || data.uncategorized_eligible === 0}
              >
                {reclassRunning ? t("items.aiEngine.classify.running") : t("items.aiEngine.classify.run")}
              </Button>
            </div>
            {!hasProfile && <p className="text-xs text-text-muted">{t("items.aiEngine.classify.needsProfile")}</p>}
            {hasProfile && data.uncategorized_eligible === 0 && (
              <p className="text-xs text-text-muted">{t("items.aiEngine.classify.nothingToDo")}</p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <JobRunStatus run={run} />
              {run?.status === "running" && <CancelActivityButton cancelUrl="/classification/reclassify/cancel" />}
            </div>
          </Card>

          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}

          <Card className="flex flex-col gap-3">
            <h2 className="text-base font-semibold text-text">{t("items.aiEngine.imports.title")}</h2>
            {data.recent_imports.length === 0 ? (
              <p className="text-sm text-text-muted">{t("items.aiEngine.imports.empty")}</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-surface-hover text-left text-xs text-text-muted">
                    <tr>
                      <th className="px-3 py-2 font-medium">{t("items.aiEngine.imports.table.file")}</th>
                      <th className="px-3 py-2 font-medium">{t("items.aiEngine.imports.table.status")}</th>
                      <th className="px-3 py-2 text-right font-medium">{t("items.aiEngine.imports.table.progress")}</th>
                      <th className="px-3 py-2 text-right font-medium">{t("items.aiEngine.imports.table.left")}</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_imports.map((item) => (
                      <tr key={item.import_id} className="border-t border-border align-top">
                        <td className="px-3 py-2">
                          <span className="text-text">{item.filename}</span>
                          {item.completed_at && (
                            <span className="block text-xs text-text-muted">{formatDateTime(item.completed_at)}</span>
                          )}
                          {item.ai_error_message && (
                            <span className="block text-xs text-danger">{item.ai_error_message}</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {item.ai_status ? (
                            <Badge tone={STATUS_TONE[item.ai_status]}>
                              {t(`items.aiEngine.imports.status.${item.ai_status}`)}
                            </Badge>
                          ) : (
                            <span className="text-text-muted">—</span>
                          )}
                        </td>
                        <td className="font-numeric px-3 py-2 text-right text-text-muted">
                          {item.ai_total > 0 ? `${item.ai_classified}/${item.ai_total}` : "—"}
                        </td>
                        <td className="font-numeric px-3 py-2 text-right text-text">{item.uncategorized_eligible}</td>
                        <td className="px-3 py-2 text-right">
                          {item.can_cancel && <CancelActivityButton cancelUrl={`/ai-engine/imports/${item.import_id}/cancel`} />}
                          {item.can_retry && (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => void onRetry(item.import_id)}
                              loading={retry.isPending && retry.variables === item.import_id}
                            >
                              {t("items.aiEngine.imports.retry")}
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-text">{t("items.aiEngine.log.title")}</h2>
            <p className="text-sm text-text-muted">{t("items.aiEngine.log.description")}</p>
          </div>
          <Select
            label={t("items.aiEngine.log.filter")}
            value={severity ?? ""}
            onChange={(event) => {
              setSeverity((event.target.value || null) as AIEventSeverity | null);
              setEventsLimit(EVENTS_PAGE_SIZE);
            }}
          >
            <option value="">{t("items.aiEngine.log.all")}</option>
            <option value="error">{t("items.aiEngine.log.severity.error")}</option>
            <option value="warning">{t("items.aiEngine.log.severity.warning")}</option>
            <option value="info">{t("items.aiEngine.log.severity.info")}</option>
          </Select>
        </div>

        {events.isLoading && <SkeletonRows rows={3} />}
        {events.isError && (
          <ErrorState message={t("items.aiEngine.log.loadError")} onRetry={() => void events.refetch()} />
        )}
        {events.data && events.data.items.length === 0 && (
          <p className="text-sm text-text-muted">{t("items.aiEngine.log.empty")}</p>
        )}
        {events.data && events.data.items.length > 0 && (
          <>
            <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">
              {events.data.items.map((event) => (
                <li key={event.id} className="flex flex-col gap-1 px-3 py-2 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={SEVERITY_TONE[event.severity]}>{t(`items.aiEngine.log.severity.${event.severity}`)}</Badge>
                    <span className="text-xs text-text-muted">{formatDateTime(event.created_at)}</span>
                    {event.import_filename && <span className="text-xs text-text-muted">· {event.import_filename}</span>}
                    {!event.import_id && event.run_kind === "reclassification" && (
                      <span className="text-xs text-text-muted">· {t("items.aiEngine.log.reclassification")}</span>
                    )}
                  </div>
                  <p className="text-text">{describeEvent(t, event)}</p>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between">
              <p className="text-xs text-text-muted">
                {t("items.aiEngine.log.shown", { shown: events.data.items.length, total: events.data.total })}
              </p>
              {events.data.items.length < events.data.total && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setEventsLimit((limit) => limit + EVENTS_PAGE_SIZE)}
                  loading={events.isFetching}
                >
                  {t("items.aiEngine.log.loadMore")}
                </Button>
              )}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
