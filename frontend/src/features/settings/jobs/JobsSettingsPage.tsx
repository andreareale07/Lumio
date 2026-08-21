import { useState } from "react";
import { Info } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";

import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { ErrorState } from "../../../components/ui/ErrorState";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import { useJobs } from "./api";
import { JobCard } from "./JobCard";

/** Pagina Impostazioni > Job — elenca tutti i job del sistema in due
 * categorie (vedi tipi in types/api.ts: JobCategory). Oggi raggiungibile da
 * qualunque utente autenticato: nessun ruolo admin di istanza esiste ancora
 * (vedi app/models/workspace_member.py), rischio accettato in attesa del
 * futuro rework — stessa scelta gia' fatta per /system-settings. */
export function JobsSettingsPage() {
  // Due namespace: "settings" resta il default per le chiavi senza
  // prefisso, "common:" per le etichette riusate altrove nell'app.
  const { t } = useTranslation(["settings", "common"]);
  const { data: jobs, isLoading, isError, refetch } = useJobs();
  const [infoOpen, setInfoOpen] = useState(false);

  const scheduledJobs = jobs?.filter((j) => j.category === "scheduled") ?? [];
  const triggeredJobs = jobs?.filter((j) => j.category === "triggered") ?? [];

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <h1 className="text-lg font-semibold text-text">{t("items.jobs.label")}</h1>
          <Button variant="ghost" size="icon" aria-label={t("items.jobs.page.infoButton")} onClick={() => setInfoOpen(true)}>
            <Info className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState message={t("items.jobs.page.loadError")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && (
        <>
          <section className="flex flex-col gap-2">
            <div>
              <h2 className="text-sm font-semibold text-text">{t("items.jobs.page.scheduled.title")}</h2>
              <p className="text-sm text-text-muted">{t("items.jobs.page.scheduled.description")}</p>
            </div>
            {scheduledJobs.map((job) => (
              <JobCard key={job.kind} job={job} />
            ))}
          </section>

          <section className="flex flex-col gap-2">
            <div>
              <h2 className="text-sm font-semibold text-text">{t("items.jobs.page.triggered.title")}</h2>
              <p className="text-sm text-text-muted">{t("items.jobs.page.triggered.description")}</p>
            </div>
            {triggeredJobs.map((job) => (
              <JobCard key={job.kind} job={job} />
            ))}
          </section>
        </>
      )}

      <Dialog open={infoOpen} onClose={() => setInfoOpen(false)} title={t("items.jobs.page.info.title")}>
        <div className="flex flex-col gap-3 text-sm text-text-muted">
          {/* Ogni paragrafo apre con un'espressione in evidenza: <Trans> lo
              tiene in una sola chiave per paragrafo, invece di spezzare la
              frase in due stringhe non traducibili separatamente. */}
          {(["scheduled", "triggered", "lock"] as const).map((key) => (
            <p key={key}>
              <Trans
                t={t}
                i18nKey={`items.jobs.page.info.${key}`}
                components={{ strong: <span className="font-medium text-text" /> }}
              />
            </p>
          ))}
        </div>
        <div className="mt-4 flex justify-end">
          <Button variant="secondary" onClick={() => setInfoOpen(false)}>
            {t("common:actions.close")}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
