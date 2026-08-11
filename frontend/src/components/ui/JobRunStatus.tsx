import type { JobRun } from "../../types/api";
import { formatDateTime } from "../../lib/format";
import { Badge } from "./Badge";

const STATUS_LABEL: Record<JobRun["status"], string> = {
  running: "In corso",
  success: "Completato",
  failed: "Non riuscito",
};
const STATUS_TONE: Record<JobRun["status"], "primary" | "success" | "danger"> = {
  running: "primary",
  success: "success",
  failed: "danger",
};

/** Stato minimo persistente di un job async innescabile manualmente
 * (refresh prezzi, ricalcolo snapshot): sopravvive a un refresh pagina, a
 * differenza di un toast effimero (gap UX emerso testando M09) — vedi
 * app/services/job_run_tracker.py sul backend. Nessun ID tecnico in vista,
 * solo stato/orario/messaggio, tutti pensati per essere letti da chi non
 * conosce l'implementazione. */
export function JobRunStatus({ run }: { run: JobRun | null | undefined }) {
  if (!run) {
    return <p className="text-sm text-text-muted">Non ancora eseguito.</p>;
  }
  const timestamp = run.finished_at ?? run.started_at;
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-text-muted">
      <Badge tone={STATUS_TONE[run.status]}>{STATUS_LABEL[run.status]}</Badge>
      <span>{formatDateTime(timestamp)}</span>
      {run.message && <span>· {run.message}</span>}
    </p>
  );
}
