import { Link, useInRouterContext } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { JobRun } from "../../types/api";
import { formatDateTime } from "../../lib/format";
import { Badge } from "./Badge";

const STATUS_TONE: Record<JobRun["status"], "primary" | "success" | "danger" | "neutral"> = {
  running: "primary",
  success: "success",
  failed: "danger",
  cancelled: "neutral",
};

/** Stato minimo persistente di un job async innescabile manualmente
 * (refresh prezzi, ricalcolo snapshot): sopravvive a un refresh pagina, a
 * differenza di un toast effimero (gap UX emerso testando M09) — vedi
 * app/services/job_run_tracker.py sul backend. Nessun ID tecnico in vista,
 * solo stato/orario/messaggio, tutti pensati per essere letti da chi non
 * conosce l'implementazione. */
export function JobRunStatus({ run }: { run: JobRun | null | undefined }) {
  const { t } = useTranslation("common");
  const inRouter = useInRouterContext();

  if (!run) {
    return <p className="text-sm text-text-muted">{t("jobRun.never")}</p>;
  }
  const timestamp = run.finished_at ?? run.started_at;
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-text-muted">
      <Badge tone={STATUS_TONE[run.status]}>{t(`jobRun.status.${run.status}`)}</Badge>
      <span>{formatDateTime(timestamp)}</span>
      {run.message && <span>· {run.message}</span>}
      {/* Un job in corso e' visibile da qualunque pagina in Attivita': senza
          questo link restava un "In corso" che non dice dove seguirlo. */}
      {run.status === "running" && inRouter && (
        <Link to="/activity" className="font-medium text-primary hover:underline">
          {t("jobRun.follow")}
        </Link>
      )}
    </p>
  );
}
