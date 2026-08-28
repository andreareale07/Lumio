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

// docs/SPEC_STOCK_PRICE.md: stessi floor/default del backend (Field(ge=...)
// in app/schemas/market_data.py) — intervallo MINIMO tra due chiamate reali
// al provider, non un TTL esatto. Validati qui solo per un feedback
// immediato, il backend resta l'autorita' (stesso vincolo lato server).
export const PORTFOLIO_REFRESH_INTERVAL_MIN = 300;
export const PORTFOLIO_REFRESH_INTERVAL_MAX = 86400;
export const DETAIL_REFRESH_INTERVAL_MIN = 5;
export const DETAIL_REFRESH_INTERVAL_MAX = 3600;

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
      // Stringa come ogni altro campo di questo form (register() raccoglie
      // sempre testo grezzo da un <input>): la conversione a numero avviene
      // al submit (MarketDataProfileFormDialog), non qui — `z.coerce.number()`
      // renderebbe il tipo INPUT del resolver `unknown`, incompatibile con
      // `useForm<MarketDataProfileFormValues>` che usa il tipo OUTPUT.
      portfolio_refresh_interval_seconds: z
        .string()
        .refine((v) => {
          const n = Number(v);
          return Number.isInteger(n) && n >= PORTFOLIO_REFRESH_INTERVAL_MIN && n <= PORTFOLIO_REFRESH_INTERVAL_MAX;
        }, t("settings:items.marketData.page.form.validation.portfolioRefreshInterval")),
      detail_refresh_interval_seconds: z
        .string()
        .refine((v) => {
          const n = Number(v);
          return Number.isInteger(n) && n >= DETAIL_REFRESH_INTERVAL_MIN && n <= DETAIL_REFRESH_INTERVAL_MAX;
        }, t("settings:items.marketData.page.form.validation.detailRefreshInterval")),
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
