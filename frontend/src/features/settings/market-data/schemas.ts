import { z } from "zod";
import type { TFunction } from "i18next";

import { MARKET_DATA_PROVIDERS, type MarketDataProviderName } from "../../../types/api";

/** Etichette/descrizioni provider: namespace "enums"/"settings" (SPEC_FE_
 * REDESIGN §27), stesso pattern di `aiProviderLabel`. */
export function marketDataProviderLabel(t: TFunction, provider: MarketDataProviderName): string {
  return t(`enums:marketDataProvider.${provider}`);
}

export function marketDataProviderDescription(t: TFunction, provider: MarketDataProviderName): string {
  return t(`settings:items.marketData.page.providerDescriptions.${provider}`);
}

// Rispecchia backend/app/services/market_data_profile_service.py
// (validate_profile_config): solo "custom" richiede endpoint + price_field.
// La API key resta SEMPRE opzionale, anche per "custom" (alcuni endpoint
// gratuiti non la richiedono) — a differenza di AI non serve quindi una
// schema factory dipendente da "e' gia' salvata una chiave?", solo da `t`.
export function buildMarketDataProfileSchema(t: TFunction) {
  return z
    .object({
      name: z.string().min(1, t("settings:items.marketData.page.form.validation.name")),
      provider: z.enum(MARKET_DATA_PROVIDERS),
      endpoint: z.string(),
      api_key: z.string(),
      price_field: z.string(),
      currency_field: z.string(),
    })
    .superRefine((data, ctx) => {
      if (data.provider === "custom") {
        if (!data.endpoint.trim()) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["endpoint"],
            message: t("settings:items.marketData.page.form.validation.endpoint"),
          });
        }
        if (!data.price_field.trim()) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["price_field"],
            message: t("settings:items.marketData.page.form.validation.priceField"),
          });
        }
      }
    });
}

export type MarketDataProfileFormValues = z.infer<ReturnType<typeof buildMarketDataProfileSchema>>;
