import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import type { TaxCodeLabel } from "./labels";

/** Render condiviso per un `TaxCodeLabel` (regime/classe asset/categoria di
 * reddito): testo tradotto normale, oppure il codice grezzo in `font-mono`
 * con un badge "non tradotto" quando la chiave i18n manca — mai una
 * stringa snake_case spacciata per etichetta (SPEC_TAX_REGIME.md). */
export function TaxCodeBadge({ value }: { value: TaxCodeLabel }) {
  const { t } = useTranslation("tax");
  if (value.isTranslated) return <>{value.label}</>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="font-mono text-text">{value.label}</span>
      <Badge tone="neutral">{t("common.untranslatedCode")}</Badge>
    </span>
  );
}
