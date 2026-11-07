import { afterEach, describe, expect, it } from "vitest";

import { formatCompactMoney, formatMoney, formatSignedMoney } from "../src/lib/format";
import { HIDDEN_AMOUNT, isAmountsHidden, setAmountsHidden } from "../src/lib/privacy";

describe("modalita' privacy", () => {
  afterEach(() => setAmountsHidden(false));

  it("mostra gli importi per default", () => {
    expect(isAmountsHidden()).toBe(false);
    expect(formatMoney(12.5, "EUR")).toContain("12");
  });

  it("nasconde ogni formato di importo quando attiva e lo ricorda", () => {
    setAmountsHidden(true);
    expect(formatMoney(12.5, "EUR")).toBe(HIDDEN_AMOUNT);
    expect(formatSignedMoney(-3, "EUR")).toBe(HIDDEN_AMOUNT);
    expect(formatCompactMoney(1500, "EUR")).toBe(HIDDEN_AMOUNT);
    expect(localStorage.getItem("lumio-hide-amounts")).toBe("1");
  });
});
