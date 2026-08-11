import type { AssetType, InvestmentTransactionType } from "../../types/api";

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
