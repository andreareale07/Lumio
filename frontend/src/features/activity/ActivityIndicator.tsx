import { useRef, useState } from "react";
import { Activity, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { BottomSheet } from "../../components/ui/BottomSheet";
import { FloatingPanel } from "../../components/ui/FloatingPanel";
import { useIsDesktop } from "../../lib/useIsDesktop";
import { isActivityRunning, useActivityPulse } from "./api";
import type { ActivityItem } from "./api";
import { CancelActivityButton } from "./CancelActivityButton";

function progressOf(item: ActivityItem): number | null {
  if (item.total == null || item.total <= 0) return null;
  return Math.min(100, Math.round(((item.processed ?? 0) / item.total) * 100));
}

/** Indicatore globale nella barra superiore: da QUALUNQUE pagina si vede se il
 * sistema sta lavorando (import, classificazione AI, riclassificazione, export,
 * ricostruzione storico...) e con un clic si arriva a seguirlo in Attivita'.
 * Risolve alla radice il "ho avviato qualcosa, ricarico la pagina e non so piu'
 * dove guardare": l'avviso non dipende dalla pagina che ha lanciato il job. */
export function ActivityIndicator() {
  const { t } = useTranslation(["activity", "jobs"]);
  const { data: items } = useActivityPulse();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const isDesktop = useIsDesktop();
  const closePanel = () => setOpen(false);

  const running = (items ?? []).filter(isActivityRunning);
  const failed = (items ?? []).filter((item) => item.status === "failed");

  const hasRunning = running.length > 0;
  const label = hasRunning
    ? t("activity:indicator.running", { count: running.length })
    : failed.length > 0
      ? t("activity:indicator.failed", { count: failed.length })
      : t("activity:indicator.idle");

  const title = t("activity:indicator.title");
  const content = (
    <div className="flex flex-col gap-3 py-2 md:py-0">
      <p className="hidden text-sm font-semibold text-text md:block">{title}</p>

      {!hasRunning && <p className="text-sm text-text-muted">{t("activity:indicator.nothingRunning")}</p>}

      {running.map((item) => {
        const percent = progressOf(item);
        return (
          <div key={`${item.kind}-${item.events_url ?? item.started_at ?? item.label}`} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="text-text">{item.label_key ? t(`jobs:${item.label_key}`) : item.label}</span>
              {item.total != null && item.total > 0 && (
                <span className="font-numeric text-xs text-text-muted">
                  {item.processed ?? 0}/{item.total}
                </span>
              )}
            </div>
            {item.cancel_url && <CancelActivityButton cancelUrl={item.cancel_url} />}
            <div
              className="h-1.5 overflow-hidden rounded-full bg-surface-hover"
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
          </div>
        );
      })}

      {failed.length > 0 && (
        <p className="text-sm text-danger">{t("activity:indicator.failedRecently", { count: failed.length })}</p>
      )}

      <Link
        to="/activity"
        onClick={closePanel}
        className="flex h-11 items-center text-sm font-medium text-primary hover:underline md:h-auto"
      >
        {t("activity:indicator.seeAll")}
      </Link>
    </div>
  );

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="dialog"
        title={label}
        className={`flex h-11 min-w-11 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-semibold hover:bg-surface-hover md:h-9 md:min-w-9 ${
          hasRunning ? "text-primary" : failed.length > 0 ? "text-danger" : "text-text-muted hover:text-text"
        }`}
      >
        {hasRunning ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Activity className="h-4 w-4" aria-hidden="true" />
        )}
        {hasRunning && <span className="font-numeric">{running.length}</span>}
        {!hasRunning && failed.length > 0 && <span className="font-numeric">{failed.length}</span>}
      </button>

      {/* Su smartphone un bottom sheet (un popover ancorato al pulsante usciva
          dallo schermo, tagliato a sinistra); su desktop un popover in portal. */}
      {isDesktop ? (
        <FloatingPanel open={open} anchorRef={buttonRef} onClose={closePanel} align="end">
          <div role="dialog" aria-label={title} className="w-80 p-3">
            {content}
          </div>
        </FloatingPanel>
      ) : (
        <BottomSheet open={open} onClose={closePanel} title={title}>
          {content}
        </BottomSheet>
      )}
    </>
  );
}
