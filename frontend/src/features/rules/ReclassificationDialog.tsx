import { useState } from "react";
import { Wand2 } from "lucide-react";
import { Link } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { JobRunStatus } from "../../components/ui/JobRunStatus";
import { Select } from "../../components/ui/Select";
import { Skeleton } from "../../components/ui/Skeleton";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { RECLASSIFICATION_SCOPES, type ReclassificationScope } from "../../types/api";
import { useCategories } from "../categories/api";
import { useCategoryLabel } from "../categories/utils";
import { useReclassificationPreview, useTriggerReclassification } from "./api";
import type { ReclassificationLive } from "./useReclassificationLive";

interface ReclassificationDialogProps {
  open: boolean;
  onClose: () => void;
  live: ReclassificationLive;
}

/** "Applica alle transazioni esistenti": le regole si applicano da sole solo
 * ai movimenti futuri, questo le rilancia sullo storico. Vive in una finestra
 * aperta da un pulsante sempre visibile in cima alla pagina (prima era un
 * pannello in fondo a una lista lunga, quindi facile da non scoprire mai).
 * Mai una scrittura silenziosa: l'anteprima mostra l'impatto prima di
 * confermare. Dopo l'avvio la finestra si chiude e il banner della pagina
 * (e l'indicatore globale) mostrano l'avanzamento. */
export function ReclassificationDialog({ open, onClose, live }: ReclassificationDialogProps) {
  const { t } = useTranslation("settings");
  return (
    <Dialog open={open} onClose={onClose} title={t("items.rules.page.reclassification.title")}>
      <ReclassificationForm onClose={onClose} live={live} />
    </Dialog>
  );
}

function ReclassificationForm({ onClose, live }: { onClose: () => void; live: ReclassificationLive }) {
  const { t } = useTranslation(["settings", "common"]);
  const categoryLabel = useCategoryLabel();
  const { data: categories } = useCategories();
  const [scope, setScope] = useState<ReclassificationScope>("uncategorized");
  const [runAi, setRunAi] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Il preview ricalcola le regole su tutte le transazioni dell'ambito: si
  // calcola solo ora che la finestra e' aperta, non al caricamento della pagina.
  const preview = useReclassificationPreview(scope);
  const trigger = useTriggerReclassification();

  const onApply = async () => {
    setError(null);
    try {
      await trigger.mutateAsync({ scope, run_ai: runAi });
      live.markStarted();
      onClose();
    } catch (failure) {
      setError(friendlyErrorMessage(failure, t("settings:items.rules.page.reclassification.error")));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">{t("settings:items.rules.page.reclassification.description")}</p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label={t("settings:items.rules.page.reclassification.scopeLabel")}
          value={scope}
          onChange={(event) => setScope(event.target.value as ReclassificationScope)}
        >
          {RECLASSIFICATION_SCOPES.map((value) => (
            <option key={value} value={value}>
              {t(`settings:items.rules.page.reclassification.scopes.${value}`)}
            </option>
          ))}
        </Select>
        <label className="flex items-end gap-2 pb-2.5 text-sm text-text-muted">
          <input
            type="checkbox"
            checked={runAi}
            onChange={(event) => setRunAi(event.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          {t("settings:items.rules.page.reclassification.useAiCheckbox")}
        </label>
      </div>

      {preview.isLoading && <Skeleton className="h-10 w-full" />}
      {preview.data && (
        <div className="rounded-lg border border-border bg-surface-hover p-3 text-sm">
          {preview.data.total_candidates === 0 ? (
            <p className="text-text-muted">{t("settings:items.rules.page.reclassification.noneInScope")}</p>
          ) : (
            <>
              <p className="text-text">
                <Trans
                  t={t}
                  i18nKey="settings:items.rules.page.reclassification.wouldChange"
                  values={{ count: preview.data.would_change, total: preview.data.total_candidates }}
                  components={{ strong: <strong /> }}
                />
              </p>
              {preview.data.breakdown.length > 0 && (
                <ul className="mt-1.5 flex max-h-48 flex-col gap-0.5 overflow-y-auto text-text-muted">
                  {preview.data.breakdown.map((item) => (
                    <li key={item.category_id}>
                      {item.count}× → {categoryLabel(categories, item.category_id) || item.category_name}
                      {item.examples.length > 0 &&
                        t("settings:items.rules.page.reclassification.breakdownExample", { example: item.examples[0] })}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}

      {live.running && (
        <p role="status" className="text-sm text-text-muted">
          {t("settings:items.rules.page.reclassification.alreadyRunning")}{" "}
          <Link to="/activity" onClick={onClose} className="font-medium text-primary hover:underline">
            {t("settings:items.rules.page.reclassification.banner.follow")}
          </Link>
        </p>
      )}

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <p className="text-xs text-text-muted">{t("settings:items.rules.page.reclassification.startedNote")}</p>

      <div className="flex flex-wrap items-center justify-between gap-2">
        {live.running ? <span /> : <JobRunStatus run={live.run} />}
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t("common:actions.cancel")}
          </Button>
          <Button
            loading={trigger.isPending}
            disabled={live.running || !preview.data || preview.data.total_candidates === 0}
            onClick={() => void onApply()}
          >
            <Wand2 className="h-4 w-4" /> {t("settings:items.rules.page.reclassification.applyNow")}
          </Button>
        </div>
      </div>
    </div>
  );
}
