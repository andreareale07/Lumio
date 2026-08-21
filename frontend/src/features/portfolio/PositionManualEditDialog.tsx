import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import type { TFunction } from "i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { useAccounts } from "../accounts/api";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import type { Position } from "../../types/api";
import { useAssets, useEditPositionManually } from "./api";
import { useAssetTypeLabel } from "./labels";

const DECIMAL_RE = /^\d+(\.\d+)?$/;

function buildSchema(t: TFunction) {
  return z.object({
    financial_account_id: z.string().min(1, t("positionDialog.validation.account")),
    asset_id: z.string().min(1, t("positionDialog.validation.asset")),
    quantity: z.string().regex(DECIMAL_RE, t("positionDialog.validation.quantity")),
    average_cost: z.string().regex(DECIMAL_RE, t("positionDialog.validation.averageCost")),
    notes: z.string().optional(),
  });
}
type FormValues = z.infer<ReturnType<typeof buildSchema>>;

interface PositionManualEditDialogProps {
  open: boolean;
  onClose: () => void;
  /** Se presente, conto/asset sono fissi (modifica di una posizione
   * esistente). Se assente, l'utente li seleziona: e' l'onboarding di una
   * posizione preesistente senza doverne ricostruire lo storico (SPEC,
   * decisione M09). */
  position?: Position | null;
}

function valuesFrom(position: Position | null | undefined): FormValues {
  if (position) {
    return {
      financial_account_id: position.financial_account_id,
      asset_id: position.asset_id,
      quantity: position.quantity,
      average_cost: position.average_cost,
      notes: "",
    };
  }
  return { financial_account_id: "", asset_id: "", quantity: "", average_cost: "", notes: "" };
}

export function PositionManualEditDialog({ open, onClose, position }: PositionManualEditDialogProps) {
  const { t } = useTranslation(["portfolio", "common"]);
  const assetTypeLabel = useAssetTypeLabel();
  const { data: accounts } = useAccounts();
  const { data: assets } = useAssets();
  const editPosition = useEditPositionManually();
  const [formError, setFormError] = useState<string | null>(null);
  const isEditing = !!position;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(buildSchema(t)), defaultValues: valuesFrom(position) });

  useEffect(() => {
    if (open) {
      reset(valuesFrom(position));
      setFormError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo su open/position
  }, [open, position]);

  const close = () => {
    setFormError(null);
    onClose();
  };

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await editPosition.mutateAsync({ ...values, notes: values.notes || null });
      close();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("positionDialog.error")));
    }
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title={isEditing ? t("positionDialog.editTitle") : t("positionDialog.createTitle")}
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-text-muted">
          {isEditing ? t("positionDialog.editHint") : t("positionDialog.createHint")}
        </p>
        <Select
          label={t("positionDialog.fields.account")}
          disabled={isEditing}
          error={errors.financial_account_id?.message}
          {...register("financial_account_id")}
        >
          <option value="">{t("positionDialog.selectAccount")}</option>
          {(accounts ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>
        <Select
          label={t("positionDialog.fields.asset")}
          disabled={isEditing}
          error={errors.asset_id?.message}
          {...register("asset_id")}
        >
          <option value="">{t("positionDialog.selectAsset")}</option>
          {(assets ?? []).map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.symbol ? `${asset.symbol} — ${asset.name}` : asset.name} ({assetTypeLabel(asset.asset_type)})
            </option>
          ))}
        </Select>
        <div className="grid grid-cols-2 gap-3">
          <Input label={t("positionDialog.fields.quantity")} error={errors.quantity?.message} {...register("quantity")} />
          <Input
            label={t("positionDialog.fields.averageCost")}
            error={errors.average_cost?.message}
            {...register("average_cost")}
          />
        </div>
        <Input label={t("positionDialog.fields.notes")} {...register("notes")} />
        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}
        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={close}>
            {t("common:actions.cancel")}
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {t("positionDialog.submit")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
