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
import { INVESTMENT_TRANSACTION_TYPES } from "../../types/api";
import { useAssets, useCreateInvestmentTransaction } from "./api";
import { ASSET_REQUIRED_TYPES, useAssetTypeLabel, useInvestmentTransactionTypeLabel } from "./labels";

const DECIMAL_RE = /^-?\d+(\.\d+)?$/;

function buildSchema(t: TFunction) {
  const decimalString = (message: string) => z.string().regex(DECIMAL_RE, message);
  return z
    .object({
      financial_account_id: z.string().min(1, t("transactionFormDialog.validation.account")),
      asset_id: z.string().optional(),
      trade_date: z.string().min(1, t("transactionFormDialog.validation.date")),
      type: z.enum(INVESTMENT_TRANSACTION_TYPES),
      quantity: z.string().optional(),
      price: z.string().optional(),
      amount: decimalString(t("transactionFormDialog.validation.amount")),
      fees: z.string().optional(),
      tax: z.string().optional(),
      currency: z.string().length(3, t("transactionFormDialog.validation.currencyLength")),
      notes: z.string().optional(),
    })
    .superRefine((values, ctx) => {
      if (ASSET_REQUIRED_TYPES.includes(values.type) && !values.asset_id) {
        ctx.addIssue({
          code: "custom",
          path: ["asset_id"],
          message: t("transactionFormDialog.validation.assetRequired"),
        });
      }
      if (values.quantity && !DECIMAL_RE.test(values.quantity)) {
        ctx.addIssue({ code: "custom", path: ["quantity"], message: t("transactionFormDialog.validation.quantity") });
      }
      if (values.price && !DECIMAL_RE.test(values.price)) {
        ctx.addIssue({ code: "custom", path: ["price"], message: t("transactionFormDialog.validation.price") });
      }
    });
}
type FormValues = z.infer<ReturnType<typeof buildSchema>>;

const DEFAULT_VALUES: FormValues = {
  financial_account_id: "",
  asset_id: "",
  trade_date: new Date().toISOString().slice(0, 10),
  type: "buy",
  quantity: "",
  price: "",
  amount: "",
  fees: "0",
  tax: "0",
  currency: "EUR",
  notes: "",
};

interface InvestmentTransactionFormDialogProps {
  open: boolean;
  onClose: () => void;
  /** Preseleziona conto/asset quando si apre da una riga già filtrata
   * (es. "+ Nuovo movimento" dentro le posizioni di un asset specifico). */
  defaultAccountId?: string;
  defaultAssetId?: string;
}

/** Libro mastro degli investimenti (SPEC §35): ogni movimento qui creato fa
 * ricalcolare la posizione derivata — mai un editing diretto della
 * posizione (vedi PositionManualEditDialog per l'onboarding senza storico). */
export function InvestmentTransactionFormDialog({
  open,
  onClose,
  defaultAccountId,
  defaultAssetId,
}: InvestmentTransactionFormDialogProps) {
  const { t } = useTranslation(["portfolio", "common"]);
  const assetTypeLabel = useAssetTypeLabel();
  const investmentTransactionTypeLabel = useInvestmentTransactionTypeLabel();
  const { data: accounts } = useAccounts();
  const { data: assets } = useAssets();
  const createTransaction = useCreateInvestmentTransaction();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(buildSchema(t)), defaultValues: DEFAULT_VALUES });

  useEffect(() => {
    if (open) {
      reset({
        ...DEFAULT_VALUES,
        financial_account_id: defaultAccountId ?? "",
        asset_id: defaultAssetId ?? "",
      });
      setFormError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo su open
  }, [open, defaultAccountId, defaultAssetId]);

  const selectedType = watch("type");
  const assetRequired = ASSET_REQUIRED_TYPES.includes(selectedType);

  const close = () => {
    setFormError(null);
    onClose();
  };

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await createTransaction.mutateAsync({
        financial_account_id: values.financial_account_id,
        asset_id: values.asset_id || null,
        trade_date: values.trade_date,
        type: values.type,
        quantity: values.quantity || null,
        price: values.price || null,
        amount: values.amount,
        fees: values.fees || "0",
        tax: values.tax || "0",
        currency: values.currency,
        notes: values.notes || null,
      });
      close();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("transactionFormDialog.error")));
    }
  };

  return (
    <Dialog open={open} onClose={close} title={t("transactionFormDialog.title")}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Select
          label={t("transactionFormDialog.fields.account")}
          error={errors.financial_account_id?.message}
          {...register("financial_account_id")}
        >
          <option value="">{t("transactionFormDialog.selectAccount")}</option>
          {(accounts ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>

        <Select label={t("transactionFormDialog.fields.type")} error={errors.type?.message} {...register("type")}>
          {INVESTMENT_TRANSACTION_TYPES.map((type) => (
            <option key={type} value={type}>
              {investmentTransactionTypeLabel(type)}
            </option>
          ))}
        </Select>

        <Select
          label={assetRequired ? t("transactionFormDialog.fields.asset") : t("transactionFormDialog.fields.assetOptional")}
          error={errors.asset_id?.message}
          {...register("asset_id")}
        >
          <option value="">
            {assetRequired ? t("transactionFormDialog.selectAssetRequired") : t("transactionFormDialog.selectAssetOptional")}
          </option>
          {(assets ?? []).map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.symbol ? `${asset.symbol} — ${asset.name}` : asset.name} ({assetTypeLabel(asset.asset_type)})
            </option>
          ))}
        </Select>

        <Input
          label={t("transactionFormDialog.fields.date")}
          type="date"
          error={errors.trade_date?.message}
          {...register("trade_date")}
        />

        <div className="grid grid-cols-2 gap-3">
          <Input
            label={t("transactionFormDialog.fields.quantity")}
            placeholder="10"
            error={errors.quantity?.message}
            {...register("quantity")}
          />
          <Input
            label={t("transactionFormDialog.fields.price")}
            placeholder="100.00"
            error={errors.price?.message}
            {...register("price")}
          />
        </div>

        <Input
          label={t("transactionFormDialog.fields.amount")}
          hint={t("transactionFormDialog.amountHint")}
          placeholder="-1000.00"
          error={errors.amount?.message}
          {...register("amount")}
        />

        <div className="grid grid-cols-2 gap-3">
          <Input label={t("transactionFormDialog.fields.fees")} {...register("fees")} />
          <Input label={t("transactionFormDialog.fields.tax")} {...register("tax")} />
        </div>

        <Input
          label={t("transactionFormDialog.fields.currency")}
          maxLength={3}
          className="uppercase"
          error={errors.currency?.message}
          {...register("currency")}
        />
        <Input label={t("transactionFormDialog.fields.notes")} {...register("notes")} />

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
            {t("transactionFormDialog.submit")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
