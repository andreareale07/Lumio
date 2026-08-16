import { useState } from "react";
import { Lock } from "lucide-react";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Dialog } from "../../../components/ui/Dialog";
import type { Job } from "../../../types/api";
import { useUpdateSystemSetting } from "./api";
import { JobParameterRow } from "./JobParameterRow";

/** Card di un singolo job — mostra il toggle on/off SOLO per i job
 * schedulati (`category === "scheduled"`): i job innescati da un'azione
 * utente non hanno un on/off di sistema qui, si gestiscono altrove (profilo
 * AI attivo per workspace, GOOGLE_ENABLED di istanza) — vedi il testo
 * dell'info nella pagina. Riattivare non chiede conferma (nessuna perdita da
 * spiegare); disattivare sì, con un testo specifico per job
 * (`job.disable_warning`). */
export function JobCard({ job }: { job: Job }) {
  const [confirmDisableOpen, setConfirmDisableOpen] = useState(false);
  const updateSetting = useUpdateSystemSetting();

  const handleToggle = async () => {
    if (job.enabled) {
      setConfirmDisableOpen(true);
      return;
    }
    await updateSetting.mutateAsync({ key: job.enabled_setting_key!, value: true });
  };

  const confirmDisable = async () => {
    await updateSetting.mutateAsync({ key: job.enabled_setting_key!, value: false });
    setConfirmDisableOpen(false);
  };

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-text">{job.name}</p>
          <p className="text-sm text-text-muted">{job.description}</p>
          {job.schedule_description && (
            <p
              className="mt-0.5 flex items-center gap-1 text-xs text-text-muted"
              title={job.schedule_readonly_reason ?? undefined}
            >
              {job.schedule_readonly_reason && <Lock className="h-3 w-3" aria-hidden="true" />}
              Cadenza: {job.schedule_description}
            </p>
          )}
        </div>
        {job.category === "scheduled" && (
          <div className="flex shrink-0 items-center gap-2">
            <Badge tone={job.enabled ? "success" : "neutral"}>{job.enabled ? "Attivo" : "Disattivato"}</Badge>
            <Button
              variant="ghost"
              size="sm"
              loading={updateSetting.isPending}
              onClick={() => void handleToggle()}
            >
              {job.enabled ? "Disattiva" : "Attiva"}
            </Button>
          </div>
        )}
      </div>

      {job.parameters.length > 0 && (
        <div className="mt-3 flex flex-col divide-y divide-border border-t border-border pt-1">
          {job.parameters.map((parameter) => (
            <JobParameterRow key={parameter.label} parameter={parameter} />
          ))}
        </div>
      )}

      <Dialog
        open={confirmDisableOpen}
        onClose={() => setConfirmDisableOpen(false)}
        title={`Disattivare "${job.name}"?`}
      >
        <p className="text-sm text-text-muted">{job.disable_warning}</p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirmDisableOpen(false)}>
            Annulla
          </Button>
          <Button variant="danger" loading={updateSetting.isPending} onClick={() => void confirmDisable()}>
            Disattiva
          </Button>
        </div>
      </Dialog>
    </Card>
  );
}
