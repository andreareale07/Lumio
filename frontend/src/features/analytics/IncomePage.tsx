import { Banknote } from "lucide-react";
import { useTranslation } from "react-i18next";

import { BreakdownPage } from "./BreakdownPage";

export function IncomePage() {
  const { t } = useTranslation("analytics");
  return (
    <BreakdownPage
      direction="income"
      title={t("income.title")}
      icon={Banknote}
      emptyDescription={t("income.emptyDescription")}
    />
  );
}
