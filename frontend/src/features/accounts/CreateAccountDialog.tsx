import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { ACCOUNT_TYPES } from "../../types/api";
import { useCreateAccount } from "./api";
import { ACCOUNT_TYPE_LABELS } from "./labels";

const schema = z.object({
  name: z.string().min(1, "Inserisci un nome"),
  account_type: z.enum(ACCOUNT_TYPES),
  currency: z.string().length(3, "Codice valuta a 3 lettere (es. EUR)"),
});
type FormValues = z.infer<typeof schema>;

export function CreateAccountDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const createAccount = useCreateAccount();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { account_type: "checking", currency: "EUR" },
  });

  const close = () => {
    reset();
    setFormError(null);
    onClose();
  };

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await createAccount.mutateAsync(values);
      close();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, "Non è stato possibile creare il conto."));
    }
  };

  return (
    <Dialog open={open} onClose={close} title="Nuovo conto">
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
            Crea conto
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
