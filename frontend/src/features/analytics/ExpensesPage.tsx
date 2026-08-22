import { Receipt } from "lucide-react";
import { useTranslation } from "react-i18next";

import { BreakdownPage } from "./BreakdownPage";

export function ExpensesPage() {
  const { t } = useTranslation("analytics");
  return (
    <BreakdownPage
      direction="expense"
      title={t("expenses.title")}
      icon={Receipt}
      emptyDescription={t("expenses.emptyDescription")}
    />
  );
}
