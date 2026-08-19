import type { Asset, AssetType, DistributionPolicy, InvestmentTransactionType } from "../../types/api";

// Etichetta da mostrare per un asset nelle liste: preferisce il symbol (se
// presente), poi il nome "pulito" dal market data provider (Step
// display_name), infine il nome grezzo del parser — mai una sovrascrittura
// di `asset.name`, solo un ordine di preferenza per la UI.
export function assetLabel(asset: Asset): string {
  return asset.symbol ?? asset.display_name ?? asset.name;
}

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  etf: "ETF",
  stock: "Azione",
  bond: "Obbligazione",
  crypto: "Crypto",
  fund: "Fondo",
  cash: "Liquidità",
  other: "Altro",
};

export const INVESTMENT_TRANSACTION_TYPE_LABELS: Record<InvestmentTransactionType, string> = {
  buy: "Acquisto",
  sell: "Vendita",
  dividend: "Dividendo",
  deposit: "Versamento",
  withdrawal: "Prelievo",
  fee: "Commissione",
  tax: "Imposta",
  split: "Frazionamento",
  opening: "Posizione iniziale",
  adjustment: "Correzione",
};

// Dedotta da un'euristica sul nome del fondo (Step 3), mai uno stato certo
// — l'etichetta lo riflette ("Accumulo (probabile)"), non lo nasconde.
export const DISTRIBUTION_POLICY_LABELS: Record<DistributionPolicy, string> = {
  accumulating: "Accumulo (probabile)",
  distributing: "Distribuzione (probabile)",
};

// Movimenti che richiedono asset + quantita' + prezzo — gli altri sono puri
// movimenti di cassa sul conto titoli (SPEC §35: deposit/withdrawal/fee
// possono non riferirsi a uno strumento).
export const ASSET_REQUIRED_TYPES: InvestmentTransactionType[] = [
  "buy",
  "sell",
  "dividend",
  "split",
  "opening",
];
