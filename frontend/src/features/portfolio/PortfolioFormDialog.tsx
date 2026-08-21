import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import type { TFunction } from "i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { CurrencyPicker } from "../settings/currency/CurrencyPicker";
import type { Portfolio } from "../../types/api";
import { useCreatePortfolio, useUpdatePortfolio } from "./api";

function buildSchema(t: TFunction) {
  return z.object({
    name: z.string().min(1, t("formDialog.validation.name")),
    description: z.string().optional(),
    // Sistema di valute: il codice viene scelto da CurrencyPicker (sempre
    // valido, mai digitato) — stesso principio gia' applicato ad
    // AccountFormDialog/AssetFormDialog, mancava solo qui.
    currency: z.string().min(2, t("formDialog.validation.currency")),
  });
}
type FormValues = z.infer<ReturnType<typeof buildSchema>>;

interface PortfolioFormDialogProps {
  open: boolean;
  onClose: () => void;
  portfolio?: Portfolio | null;
}

function valuesFrom(portfolio: Portfolio | null | undefined): FormValues {
  if (portfolio) {
    return { name: portfolio.name, description: portfolio.description ?? "", currency: portfolio.currency };
  }
  return { name: "", description: "", currency: "EUR" };
}

/** Un portfolio aggrega piu' conti sotto un nome (SPEC §36) — "Tutti i conti"
 * resta una vista implicita, non richiede un portfolio dedicato. */
export function PortfolioFormDialog({ open, onClose, portfolio }: PortfolioFormDialogProps) {
  const { t } = useTranslation(["portfolio", "common"]);
  const createPortfolio = useCreatePortfolio();
  const updatePortfolio = useUpdatePortfolio();
  const [formError, setFormError] = useState<string | null>(null);
  const isEditing = !!portfolio;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(buildSchema(t)), defaultValues: valuesFrom(portfolio) });

  useEffect(() => {
    if (open) {
      reset(valuesFrom(portfolio));
      setFormError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo su open/portfolio
  }, [open, portfolio]);

  const close = () => {
    setFormError(null);
    onClose();
  };

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    const payload = { ...values, description: values.description || null };
    try {
      if (isEditing) {
        await updatePortfolio.mutateAsync({ id: portfolio.id, ...payload });
      } else {
        await createPortfolio.mutateAsync(payload);
      }
      close();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("formDialog.error")));
    }
  };

  return (
    <Dialog open={open} onClose={close} title={isEditing ? t("formDialog.editTitle") : t("formDialog.createTitle")}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label={t("formDialog.fields.name")} error={errors.name?.message} {...register("name")} />
        <Input label={t("formDialog.fields.description")} {...register("description")} />
        <CurrencyPicker error={errors.currency?.message} {...register("currency")} />
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
            {isEditing ? t("formDialog.submitEdit") : t("formDialog.submitCreate")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
