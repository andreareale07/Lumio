import { useEffect, useState } from "react";
import { Info, Loader2 } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";

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
  // Due namespace: "settings" resta il default (chiavi senza prefisso), le
  // etichette riusate altrove nell'app arrivano da "common:".
  const { t } = useTranslation(["settings", "common"]);
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
      setError(friendlyErrorMessage(err, t("items.currency.page.saveError")));
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center gap-1.5">
        <h1 className="text-lg font-semibold text-text">{t("items.currency.label")}</h1>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("items.currency.page.infoButton")}
          onClick={() => setInfoOpen(true)}
        >
          <Info className="h-4 w-4" />
        </Button>
      </div>

      {isLoading && <SkeletonRows rows={2} />}
      {isError && <ErrorState message={t("errors.loadFailed")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && workspace && (
        <Card className="flex flex-col gap-3">
          <div>
            <p className="font-medium text-text">{t("items.currency.page.baseCurrency.label")}</p>
            <p className="text-sm text-text-muted">{t("items.currency.page.baseCurrency.description")}</p>
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
          {saved && <p className="text-sm text-success">{t("items.currency.page.saved")}</p>}
          <Button
            size="sm"
            className="self-start"
            loading={updateCurrency.isPending}
            disabled={selected === workspace.base_currency}
            onClick={() => void onSave()}
          >
            {t("common:actions.save")}
          </Button>
          {saved && (
            <div>
              <p className="flex items-center gap-1.5 text-sm text-text-muted">
                {t("items.currency.page.fxRefresh")}
                {refreshStatus.data?.status === "running" && (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                )}
              </p>
              <JobRunStatus run={refreshStatus.data} />
            </div>
          )}
        </Card>
      )}

      <Dialog open={infoOpen} onClose={() => setInfoOpen(false)} title={t("items.currency.page.info.title")}>
        <div className="flex flex-col gap-3 text-sm text-text-muted">
          <p>
            {/* Enfasi in mezzo alla frase: <Trans> tiene la frase INTERA in
                una sola chiave (l'ordine delle parole cambia da lingua a
                lingua, spezzarla in tre pezzi la renderebbe intraducibile). */}
            <Trans
              t={t}
              i18nKey="items.currency.page.info.aggregated"
              components={{ strong: <span className="font-medium text-text" /> }}
            />
          </p>
          <p>{t("items.currency.page.info.originalPreserved")}</p>
          <p>{t("items.currency.page.info.missingRate")}</p>
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
