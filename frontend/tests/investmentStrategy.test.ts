import { describe, expect, it } from "vitest";

import { classifyInvestmentStrategy } from "../src/features/portfolio/investmentStrategy";

describe("classifyInvestmentStrategy", () => {
  it("riconosce un versamento PAC", () => {
    expect(classifyInvestmentStrategy("Savings plan execution")).toBe("recurring_plan");
  });

  it("riconosce un acquisto/vendita una tantum", () => {
    expect(classifyInvestmentStrategy("Buy trade")).toBe("one_off");
    expect(classifyInvestmentStrategy("Sell trade")).toBe("one_off");
  });

  it("ignora maiuscole/minuscole e spazi", () => {
    expect(classifyInvestmentStrategy("  SAVINGS PLAN EXECUTION  ")).toBe("recurring_plan");
  });

  it("un'etichetta non riconosciuta o assente ricade su 'other', mai un'assunzione", () => {
    expect(classifyInvestmentStrategy("Qualcos'altro")).toBe("other");
    expect(classifyInvestmentStrategy(null)).toBe("other");
  });
});
