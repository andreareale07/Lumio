/** Speculare a `app/services/investment_strategy.py` — usato per filtrare
 * client-side le `InvestmentTransaction` di una strategia nel drill-down
 * (il backend non espone un filtro per questo campo derivato, solo
 * l'aggregato in `by_strategy`). Stesso principio: un'etichetta non
 * riconosciuta ricade onestamente su "other", mai un'assunzione. */
export type InvestmentStrategy = "recurring_plan" | "one_off" | "other";

const LABEL_TO_STRATEGY: Record<string, InvestmentStrategy> = {
  "savings plan execution": "recurring_plan",
  "buy trade": "one_off",
  "sell trade": "one_off",
};

export function classifyInvestmentStrategy(sourceTypeRaw: string | null): InvestmentStrategy {
  if (!sourceTypeRaw) return "other";
  const normalized = sourceTypeRaw.trim().toLowerCase().split(/\s+/).join(" ");
  return LABEL_TO_STRATEGY[normalized] ?? "other";
}
