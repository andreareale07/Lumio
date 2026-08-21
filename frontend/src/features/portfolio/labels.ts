import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import type { Asset, AssetType, DistributionPolicy, InvestmentTransactionType } from "../../types/api";

// Etichetta da mostrare per un asset nelle liste: preferisce il symbol (se
// presente), poi il nome "pulito" dal market data provider (Step
// display_name), infine il nome grezzo del parser — mai una sovrascrittura
// di `asset.name`, solo un ordine di preferenza per la UI.
export function assetLabel(asset: Asset): string {
  return asset.symbol ?? asset.display_name ?? asset.name;
}

/** Etichette enum: namespace "enums" (SPEC_FE_REDESIGN §27), stesso
 * pattern di `useTransactionTypeLabel`/`useAccountTypeLabel`. */
export function useAssetTypeLabel(): (type: AssetType) => string {
  const { t } = useTranslation("enums");
  return (type) => t(`assetType.${type}`);
}

export function useInvestmentTransactionTypeLabel(): (type: InvestmentTransactionType) => string {
  const { t } = useTranslation("enums");
  return (type) => t(`investmentTransactionType.${type}`);
}

/** Dedotta da un'euristica sul nome del fondo (Step 3), mai uno stato certo
 * — presa come funzione (non hook) perche' consumata da `AssetDetailPage`
 * dentro un array di righe costruito fuori da JSX, dove `t` e' gia'
 * disponibile dal componente chiamante. */
export function distributionPolicyLabel(t: TFunction, policy: DistributionPolicy): string {
  return t(`enums:distributionPolicy.${policy}`);
}

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
