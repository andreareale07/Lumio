import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import {
  useDeleteTaxAssetClassification,
  useSetTaxAssetClassification,
  useTaxAssetClassifications,
  useTaxRuleset,
} from "./api";
import { useTaxAssetClassLabel } from "./labels";
import { TaxCodeBadge } from "./TaxCodeBadge";

/** Card autonoma su `AssetDetailPage` (SPEC_TAX_REGIME.md FETTA 1) —
 * deliberatamente NON dentro `AssetInfoCard` (che fa `return null` quando
 * manca il profilo arricchito): la classificazione fiscale deve essere
 * sempre visibile, anche senza arricchimento provider. */
export function AssetTaxCard({ assetId }: { assetId: string }) {
  const { t } = useTranslation("tax");
  const today = new Date().toISOString().slice(0, 10);
  const { data: classifications } = useTaxAssetClassifications(today);
  const view = classifications?.find((c) => c.asset_id === assetId);
  const assetClassLabel = useTaxAssetClassLabel();
  const [dialogOpen, setDialogOpen] = useState(false);

  if (!view || view.asset_class === null) return null;

  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text">{t("asset.card.title")}</h3>
        <Button variant="ghost" size="sm" onClick={() => setDialogOpen(true)}>
          {t("asset.card.change")}
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-text">
          <TaxCodeBadge value={assetClassLabel(view.asset_class)} />
        </span>
        <Badge tone={view.is_override ? "primary" : "neutral"}>
          {view.is_override ? t("asset.card.overrideBadge") : t("asset.card.derivedBadge")}
        </Badge>
        {!view.codified && <Badge tone="warning">{t("asset.card.notCodifiedBadge")}</Badge>}
      </div>
      <AssetTaxClassificationDialog
        assetId={assetId}
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        currentClass={view.asset_class}
        isOverride={view.is_override}
        on={today}
      />
    </Card>
  );
}

function AssetTaxClassificationDialog({
  assetId,
  open,
  onClose,
  currentClass,
  isOverride,
  on,
}: {
  assetId: string;
  open: boolean;
  onClose: () => void;
  currentClass: string;
  isOverride: boolean;
  on: string;
}) {
  const { t } = useTranslation("tax");
  const { data: ruleset } = useTaxRuleset(on);
  const assetClassLabel = useTaxAssetClassLabel();
  const setClassification = useSetTaxAssetClassification(on);
  const deleteOverride = useDeleteTaxAssetClassification(on);
  const [selected, setSelected] = useState(currentClass);
  const [error, setError] = useState<string | null>(null);

  const onSave = async () => {
    setError(null);
    try {
      await setClassification.mutateAsync({ assetId, asset_class: selected });
      onClose();
    } catch (err) {
      setError(friendlyErrorMessage(err, t("asset.card.saveError")));
    }
  };

  const onResetToDerived = async () => {
    setError(null);
    try {
      await deleteOverride.mutateAsync(assetId);
      onClose();
    } catch (err) {
      setError(friendlyErrorMessage(err, t("asset.card.saveError")));
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={t("asset.card.dialogTitle")}>
      <p className="text-sm text-text-muted">{t("asset.card.dialogDescription")}</p>
      <div className="mt-4">
        <Select label={t("asset.card.classLabel")} value={selected} onChange={(e) => setSelected(e.target.value)}>
          {(ruleset?.asset_classes ?? []).map((c) => (
            <option key={c.code} value={c.code}>
              {assetClassLabel(c.code).label}
            </option>
          ))}
        </Select>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
      <div className="mt-4 flex justify-end gap-2">
        {isOverride && (
          <Button variant="ghost" loading={deleteOverride.isPending} onClick={() => void onResetToDerived()}>
            {t("asset.card.resetToDerived")}
          </Button>
        )}
        <Button variant="secondary" onClick={onClose}>
          {t("lossPocket.openingDialog.cancel")}
        </Button>
        <Button loading={setClassification.isPending} onClick={() => void onSave()}>
          {t("asset.card.save")}
        </Button>
      </div>
    </Dialog>
  );
}
