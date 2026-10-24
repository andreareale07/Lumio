import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { AssetPicker } from "./AssetPicker";
import { useMergeAssets } from "./api";
import { ratioToUnits } from "./corporateActions";

const POSITIVE_NUMBER_RE = /^\d+(\.\d+)?$/;

export interface MergeAssetsPrefill {
  sourceAssetId?: string;
  targetAssetId?: string;
  ratio?: string;
  splitDate?: string;
}

interface MergeAssetsDialogProps {
  open: boolean;
  onClose: () => void;
  prefill?: MergeAssetsPrefill;
}

export function MergeAssetsDialog({ open, onClose, prefill }: MergeAssetsDialogProps) {
  const { t } = useTranslation(["portfolio", "common"]);
  const mergeAssets = useMergeAssets();
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [oldUnits, setOldUnits] = useState("1");
  const [newUnits, setNewUnits] = useState("1");
  const [splitDate, setSplitDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    const units = ratioToUnits(prefill?.ratio ?? "1");
    setSourceId(prefill?.sourceAssetId ?? "");
    setTargetId(prefill?.targetAssetId ?? "");
    setOldUnits(units.oldUnits);
    setNewUnits(units.newUnits);
    setSplitDate(prefill?.splitDate ?? "");
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset solo all'apertura: `prefill` e' un oggetto nuovo ad ogni render del chiamante e azzererebbe le modifiche dell'utente
  }, [open]);

  const validate = (): string | null => {
    if (!sourceId) return t("portfolio:corporateActions.mergeDialog.validation.source");
    if (!targetId) return t("portfolio:corporateActions.mergeDialog.validation.target");
    if (sourceId === targetId) return t("portfolio:corporateActions.mergeDialog.validation.different");
    if (!POSITIVE_NUMBER_RE.test(oldUnits) || Number(oldUnits) <= 0) {
      return t("portfolio:corporateActions.mergeDialog.validation.units");
    }
    if (!POSITIVE_NUMBER_RE.test(newUnits) || Number(newUnits) <= 0) {
      return t("portfolio:corporateActions.mergeDialog.validation.units");
    }
    return null;
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const ratio = (Number(newUnits) / Number(oldUnits)).toFixed(10).replace(/0+$/, "").replace(/\.$/, "");
      await mergeAssets.mutateAsync({
        source_asset_id: sourceId,
        target_asset_id: targetId,
        ratio,
        split_date: splitDate || null,
      });
      onClose();
    } catch (failure) {
      setError(friendlyErrorMessage(failure, t("portfolio:corporateActions.mergeDialog.error")));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={t("portfolio:corporateActions.mergeDialog.title")}>
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-text-muted">{t("portfolio:corporateActions.mergeDialog.hint")}</p>
        <AssetPicker
          label={t("portfolio:corporateActions.mergeDialog.fields.source")}
          name="source_asset_id"
          value={sourceId}
          onChange={(event) => setSourceId(event.target.value)}
        />
        <AssetPicker
          label={t("portfolio:corporateActions.mergeDialog.fields.target")}
          name="target_asset_id"
          value={targetId}
          onChange={(event) => setTargetId(event.target.value)}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input
            label={t("portfolio:corporateActions.mergeDialog.fields.oldUnits")}
            inputMode="decimal"
            value={oldUnits}
            onChange={(event) => setOldUnits(event.target.value)}
          />
          <Input
            label={t("portfolio:corporateActions.mergeDialog.fields.newUnits")}
            inputMode="decimal"
            value={newUnits}
            onChange={(event) => setNewUnits(event.target.value)}
          />
        </div>
        <p className="text-sm text-text-muted">
          {t("portfolio:corporateActions.mergeDialog.ratioPreview", { old: oldUnits, new: newUnits })}
        </p>
        <Input
          label={t("portfolio:corporateActions.mergeDialog.fields.splitDate")}
          type="date"
          value={splitDate}
          onChange={(event) => setSplitDate(event.target.value)}
        />
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t("common:actions.cancel")}
          </Button>
          <Button type="submit" loading={submitting}>
            {t("portfolio:corporateActions.mergeDialog.submit")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
