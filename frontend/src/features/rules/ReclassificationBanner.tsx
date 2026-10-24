import { Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useEtaEstimate, type EtaLabelStrings } from "../../lib/eta";
import { CancelActivityButton } from "../activity/CancelActivityButton";
import type { ReclassificationLive } from "./useReclassificationLive";

/** Avviso in cima alla pagina mentre una riclassificazione e' in corso:
 * avanzamento, tempo residuo e il link per seguirla in Attivita'. Visibile
 * anche dopo un ricaricamento, indipendentemente da dove e' stata avviata. */
export function ReclassificationBanner({ live }: { live: ReclassificationLive }) {
  const { t } = useTranslation(["settings", "common"]);
  const etaLabels: EtaLabelStrings = {
    lessThanAMinute: () => t("common:eta.lessThanAMinute"),
    minutes: (count) => t("common:eta.minutes", { count }),
    hours: (hours, minutes) =>
      minutes > 0 ? t("common:eta.hoursMinutes", { hours, minutes }) : t("common:eta.hours", { hours }),
  };
  const eta = useEtaEstimate(live.progress?.processed ?? null, live.progress?.total ?? null, live.run?.started_at ?? null, etaLabels);

  if (!live.running) return null;

  const percent =
    live.progress && live.progress.total > 0
      ? Math.min(100, Math.round((live.progress.processed / live.progress.total) * 100))
      : null;

  return (
    <div
      role="status"
      className="flex flex-col gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 flex-col gap-1.5">
        <p className="flex items-center gap-2 text-sm font-medium text-text">
          <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
          {t("settings:items.rules.page.reclassification.banner.title")}
          <span className="font-numeric font-normal text-text-muted">
            {live.progress
              ? t("settings:items.rules.page.reclassification.banner.progress", {
                  processed: live.progress.processed,
                  total: live.progress.total,
                })
              : t("settings:items.rules.page.reclassification.banner.starting")}
            {eta && ` · ${eta.label}`}
          </span>
        </p>
        <div
          className="h-1.5 w-full max-w-md overflow-hidden rounded-full bg-surface-hover"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent ?? undefined}
        >
          <div
            className={`h-full rounded-full bg-primary ${percent === null ? "w-1/3 animate-pulse" : ""}`}
            style={percent === null ? undefined : { width: `${percent}%` }}
          />
        </div>
        {live.progress?.detail && <p className="truncate text-xs text-text-muted">{live.progress.detail}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {live.run?.status === "running" && <CancelActivityButton cancelUrl="/classification/reclassify/cancel" />}
        <Link to="/activity" className="text-sm font-medium text-primary hover:underline">
          {t("settings:items.rules.page.reclassification.banner.follow")}
        </Link>
      </div>
    </div>
  );
}
