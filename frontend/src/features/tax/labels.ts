import { useTranslation } from "react-i18next";

export interface TaxCodeLabel {
  label: string;
  isTranslated: boolean;
}

/** I regimi/classi fiscali/categorie di reddito NON sono un enum frontend
 * (SPEC_TAX_REGIME.md): sono liste dichiarate dal backend
 * (`TaxJurisdiction`), possono crescere senza un rilascio frontend. Se la
 * chiave i18n manca, il chiamante deve mostrare il CODICE grezzo in
 * `font-mono` con un badge "non tradotto" (vedi `TaxCodeBadge`) — mai una
 * stringa snake_case travestita da etichetta tradotta. */
function useTaxCodeLabel(prefix: string): (code: string) => TaxCodeLabel {
  const { t } = useTranslation("enums");
  return (code: string) => {
    const label = t(`${prefix}.${code}`, { defaultValue: "" });
    return label ? { label, isTranslated: true } : { label: code, isTranslated: false };
  };
}

export function useTaxRegimeLabel(): (code: string) => TaxCodeLabel {
  return useTaxCodeLabel("taxRegime");
}

export function useTaxAssetClassLabel(): (code: string) => TaxCodeLabel {
  return useTaxCodeLabel("taxAssetClassification");
}

export function useTaxIncomeCategoryLabel(): (code: string) => TaxCodeLabel {
  return useTaxCodeLabel("taxIncomeCategory");
}

export function useTaxJurisdictionLabel(): (code: string) => TaxCodeLabel {
  return useTaxCodeLabel("taxJurisdiction");
}
