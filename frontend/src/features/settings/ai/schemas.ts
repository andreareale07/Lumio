import { z } from "zod";

import { AI_PROVIDERS, type AIProvider } from "../../../types/api";

export const AI_PROVIDER_LABELS: Record<AIProvider, string> = {
  ollama: "Ollama (locale)",
  openai: "OpenAI",
  anthropic: "Anthropic",
  custom: "Server personalizzato",
};

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
export function buildAIProfileSchema(apiKeySet: boolean) {
  return z
    .object({
      name: z.string().min(1, "Inserisci un nome"),
      provider: z.enum(AI_PROVIDERS),
      endpoint: z.string(),
      model: z.string(),
      api_key: z.string(),
    })
    .superRefine((data, ctx) => {
      if ((data.provider === "ollama" || data.provider === "custom") && !data.endpoint.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["endpoint"], message: "Inserisci l'endpoint" });
      }
      if (data.provider === "ollama" && !data.model.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["model"], message: "Inserisci il modello" });
      }
      if (data.provider === "openai" || data.provider === "anthropic") {
        if (!apiKeySet && !data.api_key.trim()) {
          ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["api_key"], message: "Inserisci una API key" });
        }
      }
    });
}

export type AIProfileFormValues = z.infer<ReturnType<typeof buildAIProfileSchema>>;
