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
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { useAuth } from "../../app/providers/AuthProvider";
import { CurrencyPicker } from "../settings/currency/CurrencyPicker";
import { ASSET_TYPES, type Asset } from "../../types/api";
import { useCreateAsset, useUpdateAsset } from "./api";
import { useAssetTypeLabel } from "./labels";

function buildSchema(t: TFunction) {
  return z.object({
    name: z.string().min(1, t("assetFormDialog.validation.name")),
    symbol: z.string().max(32).optional(),
    isin: z.string().max(12).optional(),
    asset_type: z.enum(ASSET_TYPES),
    // Sistema di valute: il codice viene scelto da CurrencyPicker (sempre
    // valido), non piu' digitato — il vincolo qui e' solo "non vuoto".
    currency: z.string().min(2, t("assetFormDialog.validation.currency")),
    notes: z.string().optional(),
  });
}
type FormValues = z.infer<ReturnType<typeof buildSchema>>;

interface AssetFormDialogProps {
  open: boolean;
  onClose: () => void;
  asset?: Asset | null;
}

function valuesFrom(asset: Asset | null | undefined, defaultCurrency: string): FormValues {
  if (asset) {
    return {
      name: asset.name,
      symbol: asset.symbol ?? "",
      isin: asset.isin ?? "",
      asset_type: asset.asset_type,
      currency: asset.currency,
      notes: asset.notes ?? "",
    };
  }
  return { name: "", symbol: "", isin: "", asset_type: "etf", currency: defaultCurrency, notes: "" };
}

/** Catalogo asset per workspace (SPEC §33): non richiede un
 * `MarketDataProvider` configurato per esistere — un asset senza
 * symbol/isin resta valorizzato solo a costo, sempre utilizzabile. */
export function AssetFormDialog({ open, onClose, asset }: AssetFormDialogProps) {
  const { t } = useTranslation(["portfolio", "common"]);
  const assetTypeLabel = useAssetTypeLabel();
  const createAsset = useCreateAsset();
  const updateAsset = useUpdateAsset();
  const { user } = useAuth();
  const defaultCurrency = user?.base_currency ?? "EUR";
  const [formError, setFormError] = useState<string | null>(null);
  const isEditing = !!asset;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(buildSchema(t)),
    defaultValues: valuesFrom(asset, defaultCurrency),
  });

  useEffect(() => {
    if (open) {
      reset(valuesFrom(asset, defaultCurrency));
      setFormError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo su open/asset
  }, [open, asset]);

  const close = () => {
    setFormError(null);
    onClose();
  };

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    const payload = {
      ...values,
      symbol: values.symbol || null,
      isin: values.isin || null,
      notes: values.notes || null,
    };
    try {
      if (isEditing) {
        await updateAsset.mutateAsync({ id: asset.id, ...payload });
      } else {
        await createAsset.mutateAsync(payload);
      }
      close();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("assetFormDialog.error")));
    }
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title={isEditing ? t("assetFormDialog.editTitle") : t("assetFormDialog.createTitle")}
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label={t("assetFormDialog.fields.name")} error={errors.name?.message} {...register("name")} />
        <div className="grid grid-cols-2 gap-3">
          <Input label={t("assetFormDialog.fields.symbol")} placeholder="VWCE" {...register("symbol")} />
          <Input label={t("assetFormDialog.fields.isin")} placeholder="IE00BK5BQT80" {...register("isin")} />
        </div>
        <Select label={t("assetFormDialog.fields.type")} error={errors.asset_type?.message} {...register("asset_type")}>
          {ASSET_TYPES.map((type) => (
            <option key={type} value={type}>
              {assetTypeLabel(type)}
            </option>
          ))}
        </Select>
        <CurrencyPicker error={errors.currency?.message} {...register("currency")} />
        <Input label={t("assetFormDialog.fields.notes")} {...register("notes")} />
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
            {isEditing ? t("assetFormDialog.submitEdit") : t("assetFormDialog.submitCreate")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
