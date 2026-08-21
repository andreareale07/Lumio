import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import { AI_PROVIDERS, type AIProfile, type AIProfileCreate, type AIProfileUpdate } from "../../../types/api";
import {
  useCreateAIProfile,
  useListDraftModels,
  useListSavedProfileModels,
  useTestDraftConnection,
  useTestSavedProfile,
  useUpdateAIProfile,
} from "./api";
import {
  aiProviderLabel,
  CLOUD_PROVIDERS,
  MODEL_DISCOVERABLE_PROVIDERS,
  buildAIProfileSchema,
  type AIProfileFormValues,
} from "./schemas";

interface AIProfileFormDialogProps {
  open: boolean;
  onClose: () => void;
  /** Se presente, il dialog modifica questo profilo invece di crearne uno nuovo. */
  profile?: AIProfile | null;
}

const DATALIST_ID = "ai-profile-model-options";

function valuesFrom(profile: AIProfile | null | undefined): AIProfileFormValues {
  if (profile) {
    return {
      name: profile.name,
      provider: profile.provider,
      endpoint: profile.endpoint ?? "",
      model: profile.model ?? "",
      api_key: "",
    };
  }
  return { name: "", provider: "ollama", endpoint: "", model: "", api_key: "" };
}

export function AIProfileFormDialog({ open, onClose, profile }: AIProfileFormDialogProps) {
  const { t } = useTranslation(["settings", "common"]);
  const isEditing = !!profile;
  const createProfile = useCreateAIProfile();
  const updateProfile = useUpdateAIProfile();
  const testDraft = useTestDraftConnection();
  const testSaved = useTestSavedProfile();
  const listDraftModels = useListDraftModels();
  const listSavedModels = useListSavedProfileModels();

  const [formError, setFormError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [modelOptions, setModelOptions] = useState<string[]>([]);

  const {
    register,
    handleSubmit,
    watch,
    getValues,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<AIProfileFormValues>({
    resolver: zodResolver(buildAIProfileSchema(isEditing ? profile.api_key_set : false, t)),
    defaultValues: valuesFrom(profile),
  });

  useEffect(() => {
    if (open) {
      reset(valuesFrom(profile));
      setFormError(null);
      setTestResult(null);
      setModelOptions([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo su open/profile
  }, [open, profile]);

  const provider = watch("provider");
  const isCloudProvider = (CLOUD_PROVIDERS as readonly string[]).includes(provider);
  const showEndpoint = provider === "ollama" || provider === "custom";
  const showModel = true;
  const showApiKey = provider === "openai" || provider === "anthropic" || provider === "custom";
  const canDiscoverModels = (MODEL_DISCOVERABLE_PROVIDERS as readonly string[]).includes(provider);
  const keepsSavedKey = isEditing && profile.api_key_set;

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    setTestResult(null);
    const trimmedKey = values.api_key.trim();
    try {
      if (isEditing) {
        const patch: AIProfileUpdate & { id: string } = {
          id: profile.id,
          name: values.name,
          endpoint: showEndpoint ? values.endpoint.trim() : null,
          model: showModel ? values.model.trim() : null,
          ...(trimmedKey ? { api_key: trimmedKey } : {}),
        };
        await updateProfile.mutateAsync(patch);
      } else {
        const create: AIProfileCreate = {
          name: values.name,
          provider: values.provider,
          endpoint: showEndpoint ? values.endpoint.trim() : null,
          model: showModel ? values.model.trim() : null,
          ...(trimmedKey ? { api_key: trimmedKey } : {}),
        };
        await createProfile.mutateAsync(create);
      }
      onClose();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("items.ai.page.form.errors.save")));
    }
  });

  // onTest/onRefreshModels leggono i valori correnti con getValues(), MAI
  // tramite handleSubmit: verificare la connessione o elencare i modelli
  // deve essere possibile PRIMA di aver scelto un modello (o anche prima di
  // aver dato un nome al profilo) — passare per la validazione zod completa
  // bloccherebbe l'elenco modelli su "Inserisci il modello" proprio nel
  // momento in cui serve a scegliere quale modello inserire. Il backend
  // applica la stessa regola (validate_connection_prerequisites, mai
  // `model`) — un endpoint/API key davvero mancanti tornano comunque come
  // esito negativo nel messaggio di risposta, non silenziosamente ignorati.
  const draftConnectionPayload = () => {
    const values = getValues();
    return {
      provider: values.provider,
      endpoint: showEndpoint ? values.endpoint.trim() : null,
      model: showModel ? values.model.trim() : null,
      api_key: values.api_key.trim() || undefined,
    };
  };

  const onTest = async () => {
    setFormError(null);
    setTestResult(null);
    try {
      const result = isEditing
        ? await testSaved.mutateAsync(profile.id)
        : await testDraft.mutateAsync(draftConnectionPayload());
      setTestResult(result);
    } catch (error) {
      setTestResult({ success: false, message: friendlyErrorMessage(error, t("items.ai.page.form.errors.test")) });
    }
  };

  const onRefreshModels = async () => {
    setFormError(null);
    try {
      const result = isEditing
        ? await listSavedModels.mutateAsync(profile.id)
        : await listDraftModels.mutateAsync(draftConnectionPayload());
      setModelOptions(result.models);
      setTestResult({ success: result.success, message: result.message });
    } catch (error) {
      setTestResult({ success: false, message: friendlyErrorMessage(error, t("items.ai.page.form.errors.models")) });
    }
  };

  const isTesting = testDraft.isPending || testSaved.isPending;
  const isRefreshingModels = listDraftModels.isPending || listSavedModels.isPending;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={isEditing ? t("items.ai.page.form.editTitle") : t("items.ai.page.form.createTitle")}
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <Input label={t("items.ai.page.form.fields.name")} error={errors.name?.message} {...register("name")} />

        <Select
          label={t("items.ai.page.form.fields.provider")}
          disabled={isEditing}
          error={errors.provider?.message}
          {...register("provider")}
        >
          {AI_PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {aiProviderLabel(t, p)}
            </option>
          ))}
        </Select>

        {showEndpoint && (
          <Input
            label={t("items.ai.page.form.fields.endpoint")}
            placeholder={
              provider === "ollama"
                ? t("items.ai.page.form.endpointPlaceholderOllama")
                : t("items.ai.page.form.endpointPlaceholderOther")
            }
            error={errors.endpoint?.message}
            {...register("endpoint")}
          />
        )}

        {showModel && (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Input
                  label={t("items.ai.page.form.fields.model")}
                  list={canDiscoverModels ? DATALIST_ID : undefined}
                  placeholder={provider === "ollama" ? t("items.ai.page.form.modelPlaceholderOllama") : undefined}
                  error={errors.model?.message}
                  {...register("model")}
                />
              </div>
              {canDiscoverModels && (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={isRefreshingModels}
                  onClick={onRefreshModels}
                >
                  {t("items.ai.page.form.refreshModels")}
                </Button>
              )}
            </div>
            {canDiscoverModels && (
              <datalist id={DATALIST_ID}>
                {modelOptions.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            )}
          </div>
        )}

        {showApiKey && (
          <Input
            label={t("items.ai.page.form.fields.apiKey")}
            type="password"
            autoComplete="off"
            placeholder={
              keepsSavedKey
                ? t("items.ai.page.form.apiKeyPlaceholderSet")
                : t("items.ai.page.form.apiKeyPlaceholderUnset")
            }
            hint={keepsSavedKey ? t("items.ai.page.form.apiKeyHintSet") : undefined}
            error={errors.api_key?.message}
            {...register("api_key")}
          />
        )}

        {isCloudProvider && (
          <p className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning">
            {t("items.ai.page.form.cloudWarning")}
          </p>
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
            {t("items.ai.page.form.testConnection")}
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {isEditing ? t("items.ai.page.form.submitEdit") : t("items.ai.page.form.submitCreate")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
