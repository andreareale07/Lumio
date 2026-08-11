import { z } from "zod";

import { MARKET_DATA_PROVIDERS, type MarketDataProviderName } from "../../../types/api";

export const MARKET_DATA_PROVIDER_LABELS: Record<MarketDataProviderName, string> = {
  manual: "Manuale (inserisco i prezzi a mano)",
  stooq: "Stooq (gratuito)",
  yahoo: "Yahoo Finance (gratuito, non ufficiale)",
  custom: "Provider personalizzato (con API key)",
};

export const MARKET_DATA_PROVIDER_DESCRIPTIONS: Record<MarketDataProviderName, string> = {
  manual: "Nessun aggiornamento automatico: aggiorni tu il prezzo di ogni asset quando vuoi.",
  // Verificato con una chiamata reale (agosto 2026): Stooq ora richiede una
  // sfida JavaScript anti-bot che un client HTTP semplice non supera —
  // "Test connessione" lo segnala onestamente come non raggiungibile, non
  // e' un bug dell'app. Descrizione aggiornata per non far perdere tempo
  // all'utente prima di scoprirlo da solo.
  stooq: "Al momento non raggiungibile: Stooq ha introdotto una protezione anti-bot che blocca le richieste automatiche. Il codice resta pronto per quando (o se) tornerà accessibile.",
  yahoo: "Aggiornamento automatico giornaliero tramite un endpoint non ufficiale — best-effort, può interrompersi senza preavviso. Verificato funzionante.",
  custom: "Configuri tu l'endpoint (es. Alpha Vantage, Twelve Data, Finnhub) e la API key: nessun servizio è integrato di default.",
};

// Rispecchia backend/app/services/market_data_profile_service.py
// (validate_profile_config): solo "custom" richiede endpoint + price_field.
// La API key resta SEMPRE opzionale, anche per "custom" (alcuni endpoint
// gratuiti non la richiedono) — a differenza di AI non serve quindi una
// schema factory dipendente da "e' gia' salvata una chiave?".
export const marketDataProfileSchema = z
  .object({
    name: z.string().min(1, "Inserisci un nome"),
    provider: z.enum(MARKET_DATA_PROVIDERS),
    endpoint: z.string(),
    api_key: z.string(),
    price_field: z.string(),
    currency_field: z.string(),
  })
  .superRefine((data, ctx) => {
    if (data.provider === "custom") {
      if (!data.endpoint.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["endpoint"], message: "Inserisci l'endpoint" });
      }
      if (!data.price_field.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["price_field"],
          message: "Inserisci il percorso del prezzo nella risposta",
        });
      }
    }
  });

export type MarketDataProfileFormValues = z.infer<typeof marketDataProfileSchema>;
