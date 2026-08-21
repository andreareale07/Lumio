import { useState } from "react";
import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation("settings");
  const { data: jobs, isLoading, isError, refetch } = useJobs();
  const [infoOpen, setInfoOpen] = useState(false);

  const scheduledJobs = jobs?.filter((j) => j.category === "scheduled") ?? [];
  const triggeredJobs = jobs?.filter((j) => j.category === "triggered") ?? [];

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <h1 className="text-lg font-semibold text-text">{t("items.jobs.label")}</h1>
          <Button variant="ghost" size="icon" aria-label="Cosa sono le due categorie?" onClick={() => setInfoOpen(true)}>
            <Info className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState message="Non siamo riusciti a caricare i job." onRetry={() => void refetch()} />}

      {!isLoading && !isError && (
        <>
          <section className="flex flex-col gap-2">
            <div>
              <h2 className="text-sm font-semibold text-text">Job schedulati</h2>
              <p className="text-sm text-text-muted">Girano automaticamente, senza bisogno di un'azione.</p>
            </div>
            {scheduledJobs.map((job) => (
              <JobCard key={job.kind} job={job} />
            ))}
          </section>

          <section className="flex flex-col gap-2">
            <div>
              <h2 className="text-sm font-semibold text-text">Job innescati da un'azione</h2>
              <p className="text-sm text-text-muted">
                Partono solo quando importi un file, attivi un profilo AI o avvii un export.
              </p>
            </div>
            {triggeredJobs.map((job) => (
              <JobCard key={job.kind} job={job} />
            ))}
          </section>
        </>
      )}

      <Dialog open={infoOpen} onClose={() => setInfoOpen(false)} title="Due categorie di job">
        <div className="flex flex-col gap-3 text-sm text-text-muted">
          <p>
            <span className="font-medium text-text">Job schedulati</span> girano da soli, a intervalli fissi (un
            cron), indipendentemente da cosa fai nell'app — per questo hanno un vero interruttore
            attivo/disattivato qui. Disattivarli ferma solo l'esecuzione automatica: dove esiste un bottone
            manuale equivalente (es. "Aggiorna ora"), quello resta sempre disponibile.
          </p>
          <p>
            <span className="font-medium text-text">Job innescati da un'azione</span> partono solo quando tu
            (o un altro utente del workspace) fai qualcosa — importi un file, attivi un profilo AI, avvii un
            export. Non hanno un interruttore di sistema qui: si abilitano o disabilitano da dove già li
            configuri (profilo AI per workspace, integrazione Google). Qui vedi solo i loro parametri operativi.
          </p>
          <p>
            <span className="font-medium text-text">Il lucchetto</span> su un parametro (inclusa la cadenza
            dei job schedulati) indica che il valore non è modificabile da qui: è fissato nel codice del
            worker e cambiarlo richiede più di un semplice salvataggio.
          </p>
        </div>
        <div className="mt-4 flex justify-end">
          <Button variant="secondary" onClick={() => setInfoOpen(false)}>
            Chiudi
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
