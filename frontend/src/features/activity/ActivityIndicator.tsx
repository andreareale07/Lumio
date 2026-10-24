import { useEffect, useRef, useState } from "react";
import { Activity, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { isActivityRunning, useActivityPulse } from "./api";
import type { ActivityItem } from "./api";

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
  const containerRef = useRef<HTMLDivElement>(null);

  const running = (items ?? []).filter(isActivityRunning);
  const failed = (items ?? []).filter((item) => item.status === "failed");

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const hasRunning = running.length > 0;
  const label = hasRunning
    ? t("activity:indicator.running", { count: running.length })
    : failed.length > 0
      ? t("activity:indicator.failed", { count: failed.length })
      : t("activity:indicator.idle");

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={label}
        aria-expanded={open}
        title={label}
        className={`flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-semibold hover:bg-surface-hover ${
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

      {open && (
        <div
          role="dialog"
          aria-label={t("activity:indicator.title")}
          className="absolute right-0 top-full z-30 mt-2 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-3 rounded-lg border border-border bg-surface p-3 shadow-lg"
        >
          <p className="text-sm font-semibold text-text">{t("activity:indicator.title")}</p>

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
            onClick={() => setOpen(false)}
            className="text-sm font-medium text-primary hover:underline"
          >
            {t("activity:indicator.seeAll")}
          </Link>
        </div>
      )}
    </div>
  );
}
