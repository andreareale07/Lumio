import { z } from "zod";
import type { TFunction } from "i18next";

import { AI_PROVIDERS, type AIProvider } from "../../../types/api";

/** Etichette provider: namespace "enums" (SPEC_FE_REDESIGN §27), condiviso
 * con qualunque altro punto dell'app che mostri lo stesso enum invece di
 * una mappa hardcoded per feature — stesso pattern di
 * `useTransactionTypeLabel`. */
export function aiProviderLabel(t: TFunction, provider: AIProvider): string {
  return t(`enums:aiProvider.${provider}`);
}

export const CLOUD_PROVIDERS: readonly AIProvider[] = ["openai", "anthropic", "custom"];

/** Provider per cui l'elenco modelli e' interrogabile dal provider stesso
 * (Ollama/OpenAI/Anthropic hanno un endpoint di discovery standard). Per
 * "custom" resta un campo di testo libero: non c'e' garanzia che un server
 * self-hosted arbitrario implementi `/models`. */
export const MODEL_DISCOVERABLE_PROVIDERS: readonly AIProvider[] = ["ollama", "openai", "anthropic"];

// Rispecchia le validazioni di backend/app/services/ai_profile_service.py
// (validate_profile_config): endpoint richiesto per ollama/custom, model per
// ollama, API key per openai/anthropic — a meno che il profilo esistente
// abbia gia' una chiave salvata (`apiKeySet`, sempre `false` in creazione:
// nulla e' ancora salvato).
//
// `t` passato dal chiamante (non un hook qui: questo modulo non e' un
// componente) — i messaggi vivono in settings:items.ai.page.form.validation,
// stessa fonte usata dalla UI del dialog per il resto del form.
export function buildAIProfileSchema(apiKeySet: boolean, t: TFunction) {
  return z
    .object({
      name: z.string().min(1, t("settings:items.ai.page.form.validation.name")),
      provider: z.enum(AI_PROVIDERS),
      endpoint: z.string(),
      model: z.string(),
      api_key: z.string(),
    })
    .superRefine((data, ctx) => {
      if ((data.provider === "ollama" || data.provider === "custom") && !data.endpoint.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["endpoint"],
          message: t("settings:items.ai.page.form.validation.endpoint"),
        });
      }
      if (data.provider === "ollama" && !data.model.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["model"],
          message: t("settings:items.ai.page.form.validation.model"),
        });
      }
      if (data.provider === "openai" || data.provider === "anthropic") {
        if (!apiKeySet && !data.api_key.trim()) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["api_key"],
            message: t("settings:items.ai.page.form.validation.apiKey"),
          });
        }
      }
    });
}

export type AIProfileFormValues = z.infer<ReturnType<typeof buildAIProfileSchema>>;
