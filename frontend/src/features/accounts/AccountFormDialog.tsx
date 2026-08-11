import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { ACCOUNT_TYPES, type FinancialAccount } from "../../types/api";
import { useCreateAccount, useUpdateAccount } from "./api";
import { ACCOUNT_TYPE_LABELS } from "./labels";

const schema = z.object({
  name: z.string().min(1, "Inserisci un nome"),
  account_type: z.enum(ACCOUNT_TYPES),
  currency: z.string().length(3, "Codice valuta a 3 lettere (es. EUR)"),
});
type FormValues = z.infer<typeof schema>;

interface AccountFormDialogProps {
  open: boolean;
  onClose: () => void;
  /** Se presente, il dialog modifica questo conto invece di crearne uno nuovo. */
  account?: FinancialAccount | null;
}

function valuesFrom(account: FinancialAccount | null | undefined): FormValues {
  if (account) {
    return { name: account.name, account_type: account.account_type, currency: account.currency };
  }
  return { name: "", account_type: "checking", currency: "EUR" };
}

/** Il tipo di conto (`account_type`) determina in quale bucket del
 * dashboard finisce il saldo — Liquidità vs Investimenti (milestone 08,
 * SPEC §18/§30) — quindi deve poter essere corretto dopo la creazione: un
 * conto Trade Republic usato anche per la spesa quotidiana (carta + saldo
 * spendibile) va registrato come conto normale, non "Conto titoli": il
 * tracciamento delle posizioni (M09, `investment_transactions`/`positions`)
 * si lega all'id del conto, non al suo `account_type`. */
export function AccountFormDialog({ open, onClose, account }: AccountFormDialogProps) {
  const createAccount = useCreateAccount();
  const updateAccount = useUpdateAccount();
  const [formError, setFormError] = useState<string | null>(null);
  const isEditing = !!account;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: valuesFrom(account),
  });

  useEffect(() => {
    if (open) {
      reset(valuesFrom(account));
      setFormError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo su open/account
  }, [open, account]);

  const close = () => {
    setFormError(null);
    onClose();
  };

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      if (isEditing) {
        await updateAccount.mutateAsync({ id: account.id, ...values });
      } else {
        await createAccount.mutateAsync(values);
      }
      close();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, "Non è stato possibile salvare il conto."));
    }
  };

  return (
    <Dialog open={open} onClose={close} title={isEditing ? "Modifica conto" : "Nuovo conto"}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label="Nome" error={errors.name?.message} {...register("name")} />
        <Select label="Tipo" error={errors.account_type?.message} {...register("account_type")}>
          {ACCOUNT_TYPES.map((type) => (
            <option key={type} value={type}>
              {ACCOUNT_TYPE_LABELS[type]}
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
            {isEditing ? "Salva" : "Crea conto"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
