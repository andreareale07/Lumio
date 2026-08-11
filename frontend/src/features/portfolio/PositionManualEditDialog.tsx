import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { useAccounts } from "../accounts/api";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import type { Position } from "../../types/api";
import { useAssets, useEditPositionManually } from "./api";
import { ASSET_TYPE_LABELS } from "./labels";

const DECIMAL_RE = /^\d+(\.\d+)?$/;

const schema = z.object({
  financial_account_id: z.string().min(1, "Seleziona un conto"),
  asset_id: z.string().min(1, "Seleziona un asset"),
  quantity: z.string().regex(DECIMAL_RE, "Quantità non valida (>= 0)"),
  average_cost: z.string().regex(DECIMAL_RE, "Costo medio non valido (>= 0)"),
  notes: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

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
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: valuesFrom(position) });

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
      setFormError(friendlyErrorMessage(error, "Non è stato possibile salvare la posizione."));
    }
  };

  return (
    <Dialog open={open} onClose={close} title={isEditing ? "Modifica posizione" : "Posizione iniziale"}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-text-muted">
          {isEditing
            ? "La differenza rispetto ai movimenti registrati verrà annotata come correzione, mantenendo lo storico coerente."
            : "Utile per iniziare a tracciare un portafoglio già esistente senza reinserire anni di storico."}
        </p>
        <Select
          label="Conto"
          disabled={isEditing}
          error={errors.financial_account_id?.message}
          {...register("financial_account_id")}
        >
          <option value="">Seleziona un conto</option>
          {(accounts ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>
        <Select label="Asset" disabled={isEditing} error={errors.asset_id?.message} {...register("asset_id")}>
          <option value="">Seleziona un asset</option>
          {(assets ?? []).map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.symbol ? `${asset.symbol} — ${asset.name}` : asset.name} ({ASSET_TYPE_LABELS[asset.asset_type]})
            </option>
          ))}
        </Select>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Quantità posseduta" error={errors.quantity?.message} {...register("quantity")} />
          <Input label="Costo medio" error={errors.average_cost?.message} {...register("average_cost")} />
        </div>
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
            Salva
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
