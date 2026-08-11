import { Receipt } from "lucide-react";

import { BreakdownPage } from "./BreakdownPage";

export function ExpensesPage() {
  return (
    <BreakdownPage
      direction="expense"
      title="Spese"
      icon={Receipt}
      emptyDescription="Le spese classificate in questo periodo appariranno qui."
    />
  );
}
