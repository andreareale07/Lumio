import { Banknote } from "lucide-react";

import { BreakdownPage } from "./BreakdownPage";

export function IncomePage() {
  return (
    <BreakdownPage
      direction="income"
      title="Entrate"
      icon={Banknote}
      emptyDescription="Le entrate classificate in questo periodo appariranno qui."
    />
  );
}
