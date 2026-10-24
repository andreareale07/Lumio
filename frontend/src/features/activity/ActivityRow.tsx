import { useEffect, useState } from "react";
import { Ban, CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { intlLocale } from "../../lib/format";
import { useEtaEstimate, type EtaLabelStrings } from "../../lib/eta";
import type { ActivityItem, ActivityProgressEvent } from "./api";
import { streamActivityItemEvents } from "./api";
import { CancelActivityButton } from "./CancelActivityButton";

const STATUS_ICON: Record<string, typeof Loader2> = {
  running: Loader2,
  pending: Clock,
  success: CheckCircle2,
  completed: CheckCircle2,
  failed: XCircle,
  cancelled: Ban,
};

// Convenzione standard di stato (semaforo): blu/azzurro = in corso o in
// attesa (notifica passiva/workflow), verde = concluso con successo, rosso
// = errore — mai il colore da solo (WCAG): sempre accoppiato a un'icona
// diversa per forma E a un'etichetta testuale, non lasciato al solo tono.
const STATUS_TONE: Record<string, "primary" | "success" | "danger" | "neutral"> = {
  running: "primary",
  pending: "primary",
  success: "success",
  completed: "success",
  failed: "danger",
  cancelled: "neutral",
};

function formatTimestamp(value: string | null): string | null {
  if (!value) return null;
  return new Date(value).toLocaleString(intlLocale(), { dateStyle: "short", timeStyle: "medium" });
}

/** Una riga del cruscotto Attività: mostra lo stato persistito subito, poi
 * — solo se l'item espone un `events_url` (job che emette eventi SSE
 * riga-per-riga) ed è ancora attivo — apre lo stream e sovrascrive
 * processed/total/detail in tempo reale, stesso pattern di
 * AiClassificationProgress.tsx ma generalizzato al kind dell'item. */
export function ActivityRow({ item }: { item: ActivityItem }) {
  const { t } = useTranslation(["activity", "jobs"]);
  const label = item.label_key ? t(`jobs:${item.label_key}`) : item.label;
  const [processed, setProcessed] = useState(item.processed);
  const [total, setTotal] = useState(item.total);
  const [detail, setDetail] = useState<string | null>(null);
  const [status, setStatus] = useState(item.status);

  const isLive = item.events_url != null && (item.status === "running" || item.status === "pending");

  useEffect(() => {
    if (!isLive || !item.events_url) return undefined;
    const controller = new AbortController();

    const handleEvent = (event: ActivityProgressEvent) => {
      if (event.processed != null) setProcessed(event.processed);
      if (event.total != null) setTotal(event.total);
      if (event.detail) setDetail(event.detail);
      else if (event.message) setDetail(event.message);
      if (event.event === "job.completed") setStatus("success");
      if (event.event === "job.failed") setStatus("failed");
      if (event.event === "job.cancelled") setStatus("cancelled");
      if (event.event === "job.completed" || event.event === "job.failed" || event.event === "job.cancelled") {
        controller.abort();
      }
    };

    streamActivityItemEvents(item.events_url, handleEvent, controller.signal).catch(() => {
      // Nessun fallback: il prossimo polling di useActivity() (5s) riporta
      // comunque lo stato persistito piu' recente.
    });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.events_url, isLive]);

  const Icon = STATUS_ICON[status] ?? Clock;
  const tone = STATUS_TONE[status] ?? "neutral";
  const iconColorClass =
    tone === "primary" ? "text-primary" : tone === "success" ? "text-success" : tone === "danger" ? "text-danger" : "text-text-muted";
  const started = formatTimestamp(item.started_at);
  const finished = formatTimestamp(item.finished_at);
  const etaLabels: EtaLabelStrings = {
    lessThanAMinute: () => t("common:eta.lessThanAMinute"),
    minutes: (count) => t("common:eta.minutes", { count }),
    hours: (hours, minutes) =>
      minutes > 0 ? t("common:eta.hoursMinutes", { hours, minutes }) : t("common:eta.hours", { hours }),
  };
  const liveEta = useEtaEstimate(processed, total, item.started_at, etaLabels);
  const eta = status === "running" ? liveEta : null;

  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${iconColorClass} ${status === "running" ? "animate-spin" : ""}`} aria-hidden="true" />
          <span className="text-sm font-medium text-text">{label}</span>
        </div>
        <div className="flex items-center gap-2">
          {(status === "running" || status === "pending") && item.cancel_url && (
            <CancelActivityButton cancelUrl={item.cancel_url} />
          )}
          <Badge tone={tone}>{t(`row.status.${status}`, { defaultValue: status })}</Badge>
        </div>
      </div>

      {total != null && total > 0 && (
        <div className="text-sm text-text-muted">
          {processed ?? 0}/{total}
          {detail ? ` — ${detail}` : ""}
          {eta ? ` (${eta.label})` : ""}
        </div>
      )}
      {(total == null || total === 0) && detail && <div className="text-sm text-text-muted">{detail}</div>}
      {!detail && item.message && <div className="text-sm text-text-muted">{item.message}</div>}

      <div className="text-xs text-text-muted">
        {started && <span>{t("row.startedAt", { value: started })}</span>}
        {finished && <span> · {t("row.finishedAt", { value: finished })}</span>}
      </div>
    </div>
  );
}
