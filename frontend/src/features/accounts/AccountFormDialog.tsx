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
import { ACCOUNT_TYPES, type FinancialAccount } from "../../types/api";
import { useAddIbanHistory, useCreateAccount, useDeleteIbanHistory, useIbanHistory, useUpdateAccount } from "./api";
import { useAccountTypeLabel } from "./labels";

// Nessun controllo di checksum IBAN in questa fase (milestone 09.5b): solo
// una sanity-check di lunghezza/charset, sufficiente a evitare un valore
// palesemente sbagliato senza inventare una validazione completa non richiesta.
const IBAN_PATTERN = /^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/;

function buildSchema(t: TFunction) {
  return z.object({
    name: z.string().min(1, t("form.validation.name")),
    account_type: z.enum(ACCOUNT_TYPES),
    // Sistema di valute: il codice viene scelto da CurrencyPicker (sempre
    // valido), non piu' digitato — il vincolo qui e' solo "non vuoto".
    currency: z.string().min(2, t("form.validation.currency")),
    iban: z
      .string()
      .trim()
      .transform((v) => v.toUpperCase().replace(/\s+/g, ""))
      .refine((v) => v === "" || IBAN_PATTERN.test(v), t("form.validation.invalidIban"))
      .optional(),
    // Lingua usata nel testo delle categorie di sistema offerte all'IA
    // durante la classificazione di questo conto (fetta 2,
    // PLAN_TAXONOMY_I18N.md) — `null` = predefinito (italiano), invariato
    // rispetto a prima di questa fetta.
    classification_language: z.enum(["it", "en"]).nullable(),
  });
}
type FormValues = z.infer<ReturnType<typeof buildSchema>>;

interface AccountFormDialogProps {
  open: boolean;
  onClose: () => void;
  /** Se presente, il dialog modifica questo conto invece di crearne uno nuovo. */
  account?: FinancialAccount | null;
}

function valuesFrom(account: FinancialAccount | null | undefined, defaultCurrency: string): FormValues {
  if (account) {
    return {
      name: account.name,
      account_type: account.account_type,
      currency: account.currency,
      iban: account.iban ?? "",
      classification_language: account.classification_language,
    };
  }
  return { name: "", account_type: "checking", currency: defaultCurrency, iban: "", classification_language: null };
}

/** Il tipo di conto (`account_type`) determina in quale bucket del
 * dashboard finisce il saldo — Liquidità vs Investimenti (milestone 08,
 * SPEC §18/§30) — quindi deve poter essere corretto dopo la creazione: un
 * conto Trade Republic usato anche per la spesa quotidiana (carta + saldo
 * spendibile) va registrato come conto normale, non "Conto titoli": il
 * tracciamento delle posizioni (M09, `investment_transactions`/`positions`)
 * si lega all'id del conto, non al suo `account_type`. */
export function AccountFormDialog({ open, onClose, account }: AccountFormDialogProps) {
  const { t } = useTranslation(["accounts", "common"]);
  const accountTypeLabel = useAccountTypeLabel();
  const createAccount = useCreateAccount();
  const updateAccount = useUpdateAccount();
  const { user } = useAuth();
  const defaultCurrency = user?.base_currency ?? "EUR";
  const [formError, setFormError] = useState<string | null>(null);
  const isEditing = !!account;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(buildSchema(t)),
    defaultValues: valuesFrom(account, defaultCurrency),
  });

  useEffect(() => {
    if (open) {
      reset(valuesFrom(account, defaultCurrency));
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
    const payload = { ...values, iban: values.iban || null };
    try {
      if (isEditing) {
        await updateAccount.mutateAsync({ id: account.id, ...payload });
      } else {
        await createAccount.mutateAsync(payload);
      }
      close();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("form.error")));
    }
  };

  return (
    <Dialog open={open} onClose={close} title={isEditing ? t("form.editTitle") : t("form.createTitle")}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label={t("form.fields.name")} error={errors.name?.message} {...register("name")} />
        <Select label={t("form.fields.type")} error={errors.account_type?.message} {...register("account_type")}>
          {ACCOUNT_TYPES.map((type) => (
            <option key={type} value={type}>
              {accountTypeLabel(type)}
            </option>
          ))}
        </Select>
        <CurrencyPicker error={errors.currency?.message} {...register("currency")} />
        <Input
          label={t("form.fields.iban")}
          className="uppercase"
          hint={t("form.ibanHint")}
          error={errors.iban?.message}
          {...register("iban")}
        />
        <div className="flex flex-col gap-1.5">
          <Select
            label={t("form.fields.classificationLanguage")}
            error={errors.classification_language?.message}
            {...register("classification_language", { setValueAs: (v) => (v === "" ? null : v) })}
          >
            <option value="">{t("form.classificationLanguageDefault")}</option>
            <option value="it">{t("common:language.it")}</option>
            <option value="en">{t("common:language.en")}</option>
          </Select>
          {!errors.classification_language && (
            <p className="text-sm text-text-muted">{t("form.classificationLanguageHint")}</p>
          )}
        </div>
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
            {isEditing ? t("form.submitEdit") : t("form.submitCreate")}
          </Button>
        </div>
      </form>
      {/* Gestione manuale distinta dal form sopra: la storicizzazione
       * automatica (useUpdateAccount) scatta solo quando il campo IBAN
       * cambia DENTRO l'app — non basta per chi imposta il conto per la
       * prima volta conoscendo gia' un IBAN precedente. */}
      {isEditing && <IbanHistorySection accountId={account.id} />}
    </Dialog>
  );
}

function IbanHistorySection({ accountId }: { accountId: string }) {
  const { t } = useTranslation("accounts");
  const { data: history } = useIbanHistory(accountId);
  const addHistory = useAddIbanHistory(accountId);
  const deleteHistory = useDeleteIbanHistory(accountId);
  const [newIban, setNewIban] = useState("");
  const [error, setError] = useState<string | null>(null);

  const onAdd = async () => {
    setError(null);
    const normalized = newIban.trim().toUpperCase().replace(/\s+/g, "");
    if (!IBAN_PATTERN.test(normalized)) {
      setError(t("form.validation.invalidIban"));
      return;
    }
    try {
      await addHistory.mutateAsync(normalized);
      setNewIban("");
    } catch (err) {
      setError(friendlyErrorMessage(err, t("form.ibanHistory.addError")));
    }
  };

  return (
    <div className="mt-4 flex flex-col gap-2 border-t border-border pt-4">
      <p className="text-sm font-medium text-text">{t("form.ibanHistory.title")}</p>
      <p className="text-sm text-text-muted">{t("form.ibanHistory.description")}</p>
      {history && history.length > 0 && (
        <ul className="flex flex-col gap-1">
          {history.map((entry) => (
            <li key={entry.id} className="flex items-center justify-between gap-2 text-sm">
              <span className="font-mono text-text">{entry.iban}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                loading={deleteHistory.isPending}
                onClick={() => deleteHistory.mutate(entry.id)}
              >
                {t("form.ibanHistory.remove")}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-center gap-2">
        <Input
          className="uppercase"
          placeholder={t("form.ibanHistory.placeholder")}
          value={newIban}
          onChange={(e) => setNewIban(e.target.value)}
        />
        <Button type="button" variant="secondary" size="sm" loading={addHistory.isPending} onClick={() => void onAdd()}>
          {t("form.ibanHistory.add")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
