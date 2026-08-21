import { useTranslation } from "react-i18next";

import type { TransactionType } from "../../types/api";

/** SPEC_FE_REDESIGN §27: un enum del backend non si mostra mai grezzo, ma la
 * sua etichetta non e' piu' una mappa italiana hardcoded qui — vive nel
 * namespace i18next "enums", condiviso da tutte le feature che mostrano lo
 * stesso enum (Transazioni, Impostazioni > Tipi di transazione). */
export function useTransactionTypeLabel(): (type: TransactionType) => string {
  const { t } = useTranslation("enums");
  return (type) => t(`transactionType.${type}`);
}
