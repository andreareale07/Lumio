import { useEffect, useState } from "react";
import { Info, Loader2 } from "lucide-react";

import { useAuth } from "../../../app/providers/AuthProvider";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Dialog } from "../../../components/ui/Dialog";
import { ErrorState } from "../../../components/ui/ErrorState";
import { JobRunStatus } from "../../../components/ui/JobRunStatus";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import { useMarketDataRefreshStatus } from "../market-data/api";
import { CurrencyPicker } from "./CurrencyPicker";
import { useUpdateWorkspaceCurrency, useWorkspace } from "./api";

/** Pagina Impostazioni > Valuta — sistema di valute: la `base_currency` del
 * workspace decide in quale valuta vengono sommati i totali aggregati
 * (patrimonio, portafoglio, entrate/uscite). Cambiarla NON riconverte nulla
 * di storico: i dati grezzi (transazioni, posizioni, prezzi) restano sempre
 * nella loro valuta originale — solo i totali si ricalcolano da quel
 * momento in poi. */
export function CurrencySettingsPage() {
  const { data: workspace, isLoading, isError, refetch } = useWorkspace();
  const updateCurrency = useUpdateWorkspaceCurrency();
  // Cambiare valuta accoda in background lo stesso job di refresh usato dal
  // pulsante "Aggiorna ora" in Impostazioni > Market Data (scarica i tassi
  // di cambio mancanti verso la nuova valuta) — riusa lo stesso stato
  // persistente cosi' l'utente vede quando il download e' completato,
  // invece di un'app che sembra "vuota" per qualche secondo senza spiegazione.
  const refreshStatus = useMarketDataRefreshStatus();
  const { refreshUser } = useAuth();
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);

  useEffect(() => {
    if (workspace) setSelected(workspace.base_currency);
  }, [workspace]);

  const onSave = async () => {
    setError(null);
    setSaved(false);
    try {
      await updateCurrency.mutateAsync(selected);
      await refreshUser();
      await refreshStatus.refetch();
      setSaved(true);
    } catch (err) {
      setError(friendlyErrorMessage(err, "Non è stato possibile cambiare la valuta."));
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center gap-1.5">
        <h1 className="text-lg font-semibold text-text">Valuta</h1>
        <Button variant="ghost" size="icon" aria-label="Cosa significa cambiare la valuta?" onClick={() => setInfoOpen(true)}>
          <Info className="h-4 w-4" />
        </Button>
      </div>

      {isLoading && <SkeletonRows rows={2} />}
      {isError && <ErrorState message="Non siamo riusciti a caricare le impostazioni." onRetry={() => void refetch()} />}

      {!isLoading && !isError && workspace && (
        <Card className="flex flex-col gap-3">
          <div>
            <p className="font-medium text-text">Valuta di riferimento</p>
            <p className="text-sm text-text-muted">
              Usata per sommare patrimonio, portafoglio ed entrate/uscite quando conti o investimenti sono in
              valute diverse. Non cambia i dati originali, solo come vengono aggregati.
            </p>
          </div>
          <CurrencyPicker
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              setSaved(false);
            }}
            disabled={updateCurrency.isPending}
          />
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          {saved && <p className="text-sm text-success">Valuta aggiornata.</p>}
          <Button
            size="sm"
            className="self-start"
            loading={updateCurrency.isPending}
            disabled={selected === workspace.base_currency}
            onClick={() => void onSave()}
          >
            Salva
          </Button>
          {saved && (
            <div>
              <p className="flex items-center gap-1.5 text-sm text-text-muted">
                Aggiornamento tassi di cambio:
                {refreshStatus.data?.status === "running" && (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                )}
              </p>
              <JobRunStatus run={refreshStatus.data} />
            </div>
          )}
        </Card>
      )}

      <Dialog open={infoOpen} onClose={() => setInfoOpen(false)} title="Cosa cambia">
        <div className="flex flex-col gap-3 text-sm text-text-muted">
          <p>
            La valuta di riferimento decide in quale valuta vengono <span className="font-medium text-text">sommati</span>{" "}
            i totali che mescolano conti/asset in valute diverse — patrimonio, valore del portafoglio,
            entrate/uscite complessive.
          </p>
          <p>
            Ogni transazione, conto e posizione conserva SEMPRE la propria valuta originale: cambiare questa
            impostazione non tocca nessun dato storico, solo il calcolo dei totali aggregati da questo momento
            in poi.
          </p>
          <p>
            Se manca un tasso di cambio per una valuta in uso, quella parte resta esclusa dal totale ma viene
            segnalata — mai un'esclusione silenziosa.
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
