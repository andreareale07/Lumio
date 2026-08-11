import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { ASSET_TYPES, type Asset } from "../../types/api";
import { useCreateAsset, useUpdateAsset } from "./api";
import { ASSET_TYPE_LABELS } from "./labels";

const schema = z.object({
  name: z.string().min(1, "Inserisci un nome"),
  symbol: z.string().max(32).optional(),
  isin: z.string().max(12).optional(),
  asset_type: z.enum(ASSET_TYPES),
  currency: z.string().length(3, "Codice valuta a 3 lettere (es. EUR)"),
  notes: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

interface AssetFormDialogProps {
  open: boolean;
  onClose: () => void;
  asset?: Asset | null;
}

function valuesFrom(asset: Asset | null | undefined): FormValues {
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
  return { name: "", symbol: "", isin: "", asset_type: "etf", currency: "EUR", notes: "" };
}

/** Catalogo asset per workspace (SPEC §33): non richiede un
 * `MarketDataProvider` configurato per esistere — un asset senza
 * symbol/isin resta valorizzato solo a costo, sempre utilizzabile. */
export function AssetFormDialog({ open, onClose, asset }: AssetFormDialogProps) {
  const createAsset = useCreateAsset();
  const updateAsset = useUpdateAsset();
  const [formError, setFormError] = useState<string | null>(null);
  const isEditing = !!asset;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: valuesFrom(asset) });

  useEffect(() => {
    if (open) {
      reset(valuesFrom(asset));
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
      setFormError(friendlyErrorMessage(error, "Non è stato possibile salvare l'asset."));
    }
  };

  return (
    <Dialog open={open} onClose={close} title={isEditing ? "Modifica asset" : "Nuovo asset"}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label="Nome" error={errors.name?.message} {...register("name")} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Simbolo (opzionale)" placeholder="VWCE" {...register("symbol")} />
          <Input label="ISIN (opzionale)" placeholder="IE00BK5BQT80" {...register("isin")} />
        </div>
        <Select label="Tipo" error={errors.asset_type?.message} {...register("asset_type")}>
          {ASSET_TYPES.map((type) => (
            <option key={type} value={type}>
              {ASSET_TYPE_LABELS[type]}
            </option>
          ))}
        </Select>
        <Input
          label="Valuta"
          maxLength={3}
          className="uppercase"
          error={errors.currency?.message}
          {...register("currency")}
        />
        <Input label="Note (opzionale)" {...register("notes")} />
        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}
        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={close}>
            Annulla
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {isEditing ? "Salva" : "Crea asset"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
