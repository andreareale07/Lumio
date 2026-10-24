import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { formatDate, formatMoney, formatQuantity } from "../../lib/format";
import type { ExpirySuggestion, SplitSuggestion } from "../../types/api";
import { ExpireAssetDialog } from "./ExpireAssetDialog";
import { MergeAssetsDialog } from "./MergeAssetsDialog";
import { useCorporateActionSuggestions } from "./api";
import { ratioToUnits } from "./corporateActions";

const DISMISSED_KEY = "lumio.corporateActions.dismissed";

// "Non e' un raggruppamento" / "E' ancora attivo" e' una comodita' per-viewer
// (nessuna correzione di dati): vive nel browser, mai in DB, e puo' sempre
// mancare (private window, storage bloccato) senza rompere la pagina.
function readDismissed(): Set<string> {
  try {
    const raw = window.localStorage.getItem(DISMISSED_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function writeDismissed(ids: Set<string>): void {
  try {
    window.localStorage.setItem(DISMISSED_KEY, JSON.stringify([...ids]));
  } catch {
    // storage non disponibile: l'avviso riapparira' al prossimo caricamento
  }
}

const splitId = (s: SplitSuggestion) => `split:${s.source_asset_id}:${s.target_asset_id}`;
const expiryId = (e: ExpirySuggestion) => `expiry:${e.asset_id}`;

/** Avvisi "Lumio ha notato" sopra la panoramica Investimenti: raggruppamenti
 * di azioni con cambio di ISIN e derivati forse scaduti. Non applica nulla da
 * solo — ogni azione passa da un dialog di conferma (le correzioni manuali
 * battono sempre l'automatismo). Non renderizza niente se non c'e' nulla da
 * segnalare. */
export function CorporateActionSuggestions() {
  const { t } = useTranslation("portfolio");
  const suggestions = useCorporateActionSuggestions();
  const [dismissed, setDismissed] = useState<Set<string>>(readDismissed);
  const [mergeTarget, setMergeTarget] = useState<SplitSuggestion | null>(null);
  const [expireTarget, setExpireTarget] = useState<ExpirySuggestion | null>(null);

  const dismiss = (id: string) => {
    const next = new Set(dismissed).add(id);
    setDismissed(next);
    writeDismissed(next);
  };

  const splits = (suggestions.data?.splits ?? []).filter((s) => !dismissed.has(splitId(s)));
  const expirations = (suggestions.data?.expirations ?? []).filter((e) => !dismissed.has(expiryId(e)));
  if (splits.length === 0 && expirations.length === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      {splits.map((split) => {
        const units = ratioToUnits(split.ratio);
        return (
          <Card key={splitId(split)} className="flex flex-col gap-2 border-warning">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-text">{t("corporateActions.split.title")}</h3>
              <Badge tone={split.confidence === "high" ? "success" : "warning"}>
                {split.confidence === "high"
                  ? t("corporateActions.split.evidenceHigh")
                  : t("corporateActions.split.evidenceMedium")}
              </Badge>
            </div>
            <p className="text-sm text-text-muted">
              {t("corporateActions.split.description", {
                source: split.source_label,
                target: split.target_label,
                sourceQuantity: formatQuantity(split.source_quantity),
                targetQuantity: formatQuantity(split.target_quantity),
                old: units.oldUnits,
                new: units.newUnits,
              })}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => setMergeTarget(split)}>
                {t("corporateActions.split.review")}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => dismiss(splitId(split))}>
                {t("corporateActions.split.dismiss")}
              </Button>
            </div>
          </Card>
        );
      })}

      {expirations.map((expiry) => (
        <Card key={expiryId(expiry)} className="flex flex-col gap-2 border-warning">
          <h3 className="text-sm font-semibold text-text">{t("corporateActions.expiry.title")}</h3>
          <p className="text-sm text-text-muted">
            {t("corporateActions.expiry.description", {
              asset: expiry.asset_label,
              quantity: formatQuantity(expiry.quantity),
              cost: formatMoney(expiry.cost_basis, expiry.currency),
            })}{" "}
            {expiry.last_price_date
              ? t("corporateActions.expiry.lastPrice", { date: formatDate(expiry.last_price_date) })
              : t("corporateActions.expiry.neverPriced")}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setExpireTarget(expiry)}>
              {t("corporateActions.expiry.expire")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => dismiss(expiryId(expiry))}>
              {t("corporateActions.expiry.stillActive")}
            </Button>
          </div>
        </Card>
      ))}

      <MergeAssetsDialog
        open={mergeTarget !== null}
        onClose={() => setMergeTarget(null)}
        prefill={
          mergeTarget
            ? {
                sourceAssetId: mergeTarget.source_asset_id,
                targetAssetId: mergeTarget.target_asset_id,
                ratio: mergeTarget.ratio,
                splitDate: mergeTarget.split_date,
              }
            : undefined
        }
      />
      <ExpireAssetDialog
        open={expireTarget !== null}
        onClose={() => setExpireTarget(null)}
        assetId={expireTarget?.asset_id ?? ""}
        assetLabel={expireTarget?.asset_label ?? ""}
      />
    </div>
  );
}
