import { useTranslation } from "react-i18next";

import type { AccountType } from "../../types/api";

/** SPEC_FE_REDESIGN §27: enum del backend, etichetta nel namespace i18next
 * "enums" condiviso — stesso pattern di `useTransactionTypeLabel`. */
export function useAccountTypeLabel(): (type: AccountType) => string {
  const { t } = useTranslation("enums");
  return (type) => t(`accountType.${type}`);
}
