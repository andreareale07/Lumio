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
import { INVESTMENT_TRANSACTION_TYPES } from "../../types/api";
import { useAssets, useCreateInvestmentTransaction } from "./api";
import { ASSET_REQUIRED_TYPES, ASSET_TYPE_LABELS, INVESTMENT_TRANSACTION_TYPE_LABELS } from "./labels";

const DECIMAL_RE = /^-?\d+(\.\d+)?$/;
const decimalString = (message: string) => z.string().regex(DECIMAL_RE, message);

const schema = z
  .object({
    financial_account_id: z.string().min(1, "Seleziona un conto"),
    asset_id: z.string().optional(),
    trade_date: z.string().min(1, "Inserisci una data"),
    type: z.enum(INVESTMENT_TRANSACTION_TYPES),
    quantity: z.string().optional(),
    price: z.string().optional(),
    amount: decimalString("Importo non valido (es. -1000.00)"),
    fees: z.string().optional(),
    tax: z.string().optional(),
    currency: z.string().length(3, "Codice valuta a 3 lettere (es. EUR)"),
    notes: z.string().optional(),
  })
  .superRefine((values, ctx) => {
    if (ASSET_REQUIRED_TYPES.includes(values.type) && !values.asset_id) {
      ctx.addIssue({ code: "custom", path: ["asset_id"], message: "Seleziona un asset per questo tipo di movimento" });
    }
    if (values.quantity && !DECIMAL_RE.test(values.quantity)) {
      ctx.addIssue({ code: "custom", path: ["quantity"], message: "Quantità non valida" });
    }
    if (values.price && !DECIMAL_RE.test(values.price)) {
      ctx.addIssue({ code: "custom", path: ["price"], message: "Prezzo non valido" });
    }
  });
type FormValues = z.infer<typeof schema>;

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
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: DEFAULT_VALUES });

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
      setFormError(friendlyErrorMessage(error, "Non è stato possibile registrare il movimento."));
    }
  };

  return (
    <Dialog open={open} onClose={close} title="Nuovo movimento">
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Select label="Conto" error={errors.financial_account_id?.message} {...register("financial_account_id")}>
          <option value="">Seleziona un conto</option>
          {(accounts ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>

        <Select label="Tipo" error={errors.type?.message} {...register("type")}>
          {INVESTMENT_TRANSACTION_TYPES.map((type) => (
            <option key={type} value={type}>
              {INVESTMENT_TRANSACTION_TYPE_LABELS[type]}
            </option>
          ))}
        </Select>

        <Select
          label={assetRequired ? "Asset" : "Asset (opzionale)"}
          error={errors.asset_id?.message}
          {...register("asset_id")}
        >
          <option value="">
            {assetRequired ? "Seleziona un asset" : "Nessuno (movimento di cassa)"}
          </option>
          {(assets ?? []).map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.symbol ? `${asset.symbol} — ${asset.name}` : asset.name} ({ASSET_TYPE_LABELS[asset.asset_type]})
            </option>
          ))}
        </Select>

        <Input label="Data" type="date" error={errors.trade_date?.message} {...register("trade_date")} />

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Quantità (opzionale)"
            placeholder="10"
            error={errors.quantity?.message}
            {...register("quantity")}
          />
          <Input
            label="Prezzo (opzionale)"
            placeholder="100.00"
            error={errors.price?.message}
            {...register("price")}
          />
        </div>

        <Input
          label="Importo netto in cassa"
          hint="Negativo se il movimento riduce la liquidità del conto (es. un acquisto)."
          placeholder="-1000.00"
          error={errors.amount?.message}
          {...register("amount")}
        />

        <div className="grid grid-cols-2 gap-3">
          <Input label="Commissioni" {...register("fees")} />
          <Input label="Imposte" {...register("tax")} />
        </div>

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
            Registra movimento
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
