import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import {
  MARKET_DATA_PROVIDERS,
  type MarketDataProfile,
  type MarketDataProfileCreate,
  type MarketDataProfileUpdate,
} from "../../../types/api";
import {
  useCreateMarketDataProfile,
  useTestDraftMarketDataConnection,
  useTestSavedMarketDataProfile,
  useUpdateMarketDataProfile,
} from "./api";
import {
  MARKET_DATA_PROVIDER_DESCRIPTIONS,
  MARKET_DATA_PROVIDER_LABELS,
  marketDataProfileSchema,
  type MarketDataProfileFormValues,
} from "./schemas";

interface MarketDataProfileFormDialogProps {
  open: boolean;
  onClose: () => void;
  profile?: MarketDataProfile | null;
}

function valuesFrom(profile: MarketDataProfile | null | undefined): MarketDataProfileFormValues {
  if (profile) {
    return {
      name: profile.name,
      provider: profile.provider,
      endpoint: profile.endpoint ?? "",
      api_key: "",
      price_field: profile.price_field ?? "",
      currency_field: profile.currency_field ?? "",
    };
  }
  return { name: "", provider: "manual", endpoint: "", api_key: "", price_field: "", currency_field: "" };
}

/** SPEC §38: manuale / gratuito (Stooq, Yahoo) / personalizzato con API key
 * — nessun provider e' obbligatorio, l'app funziona anche senza nessuno
 * attivo (valorizzazione a costo storico). */
export function MarketDataProfileFormDialog({ open, onClose, profile }: MarketDataProfileFormDialogProps) {
  const isEditing = !!profile;
  const createProfile = useCreateMarketDataProfile();
  const updateProfile = useUpdateMarketDataProfile();
  const testDraft = useTestDraftMarketDataConnection();
  const testSaved = useTestSavedMarketDataProfile();

  const [formError, setFormError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    getValues,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<MarketDataProfileFormValues>({
    resolver: zodResolver(marketDataProfileSchema),
    defaultValues: valuesFrom(profile),
  });

  useEffect(() => {
    if (open) {
      reset(valuesFrom(profile));
      setFormError(null);
      setTestResult(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo su open/profile
  }, [open, profile]);

  const provider = watch("provider");
  const isCustom = provider === "custom";
  const keepsSavedKey = isEditing && profile.api_key_set;

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    setTestResult(null);
    const trimmedKey = values.api_key.trim();
    try {
      if (isEditing) {
        const patch: MarketDataProfileUpdate & { id: string } = {
          id: profile.id,
          name: values.name,
          endpoint: isCustom ? values.endpoint.trim() : null,
          price_field: isCustom ? values.price_field.trim() : null,
          currency_field: isCustom ? values.currency_field.trim() || null : null,
          ...(trimmedKey ? { api_key: trimmedKey } : {}),
        };
        await updateProfile.mutateAsync(patch);
      } else {
        const create: MarketDataProfileCreate = {
          name: values.name,
          provider: values.provider,
          endpoint: isCustom ? values.endpoint.trim() : null,
          price_field: isCustom ? values.price_field.trim() : null,
          currency_field: isCustom ? values.currency_field.trim() || null : null,
          ...(trimmedKey ? { api_key: trimmedKey } : {}),
        };
        await createProfile.mutateAsync(create);
      }
      onClose();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, "Non è stato possibile salvare il profilo."));
    }
  });

  // Stesso principio di AIProfileFormDialog: il test legge i valori
  // correnti con getValues(), mai tramite handleSubmit — verificare la
  // connessione deve essere possibile senza aver ancora compilato tutto il
  // form (es. prima di aver dato un nome al profilo).
  const onTest = async () => {
    setFormError(null);
    setTestResult(null);
    try {
      const result = isEditing
        ? await testSaved.mutateAsync(profile.id)
        : await testDraft.mutateAsync({
            provider: getValues("provider"),
            endpoint: isCustom ? getValues("endpoint").trim() : null,
            api_key: getValues("api_key").trim() || undefined,
            price_field: isCustom ? getValues("price_field").trim() : null,
            currency_field: isCustom ? getValues("currency_field").trim() || null : null,
          });
      setTestResult(result);
    } catch (error) {
      setTestResult({ success: false, message: friendlyErrorMessage(error, "Verifica non riuscita.") });
    }
  };

  const isTesting = testDraft.isPending || testSaved.isPending;

  return (
    <Dialog open={open} onClose={onClose} title={isEditing ? "Modifica profilo" : "Nuovo profilo market data"}>
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <Input label="Nome" error={errors.name?.message} {...register("name")} />

        <Select label="Provider" disabled={isEditing} error={errors.provider?.message} {...register("provider")}>
          {MARKET_DATA_PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {MARKET_DATA_PROVIDER_LABELS[p]}
            </option>
          ))}
        </Select>
        <p className="text-sm text-text-muted">{MARKET_DATA_PROVIDER_DESCRIPTIONS[provider]}</p>

        {isCustom && (
          <>
            <Input
              label="Endpoint"
              placeholder="https://api.esempio.com/quote?symbol={symbol}"
              hint="Usa {symbol} come segnaposto per il simbolo dell'asset."
              error={errors.endpoint?.message}
              {...register("endpoint")}
            />
            <Input
              label="API key (opzionale)"
              type="password"
              autoComplete="off"
              placeholder={keepsSavedKey ? "•••••••••• (configurata)" : ""}
              hint={keepsSavedKey ? "Lascia vuoto per mantenere la chiave salvata." : undefined}
              {...register("api_key")}
            />
            <Input
              label="Percorso del prezzo nella risposta"
              placeholder="price"
              hint='Percorso puntato nel JSON di risposta, es. "quote.price".'
              error={errors.price_field?.message}
              {...register("price_field")}
            />
            <Input
              label="Percorso della valuta (opzionale)"
              placeholder="currency"
              hint="Se vuoto, si usa la valuta dell'asset."
              {...register("currency_field")}
            />
          </>
        )}

        {testResult && (
          <p role="status" className={`text-sm ${testResult.success ? "text-success" : "text-danger"}`}>
            {testResult.message}
          </p>
        )}
        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}

        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="secondary" loading={isTesting} onClick={onTest}>
            Verifica connessione
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {isEditing ? "Salva" : "Crea profilo"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
