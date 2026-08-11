import { describe, expect, it } from "vitest";

import { resolvePeriodPreset } from "../src/lib/period";

const TODAY = new Date(2026, 7, 15); // 15 agosto 2026 (mese 0-indexed)

describe("resolvePeriodPreset", () => {
  it("questo mese va dal primo del mese a oggi", () => {
    expect(resolvePeriodPreset("this_month", TODAY)).toEqual({
      date_from: "2026-08-01",
      date_to: "2026-08-15",
    });
  });

  it("mese scorso e' l'intero mese precedente", () => {
    expect(resolvePeriodPreset("last_month", TODAY)).toEqual({
      date_from: "2026-07-01",
      date_to: "2026-07-31",
    });
  });

  it("mese scorso a cavallo di anno resta corretto", () => {
    const jan15 = new Date(2026, 0, 15);
    expect(resolvePeriodPreset("last_month", jan15)).toEqual({
      date_from: "2025-12-01",
      date_to: "2025-12-31",
    });
  });

  it("ultimi 3 mesi va da 3 mesi fa a oggi", () => {
    expect(resolvePeriodPreset("last_3_months", TODAY)).toEqual({
      date_from: "2026-05-15",
      date_to: "2026-08-15",
    });
  });

  it("ultimi 6 mesi va da 6 mesi fa a oggi", () => {
    expect(resolvePeriodPreset("last_6_months", TODAY)).toEqual({
      date_from: "2026-02-15",
      date_to: "2026-08-15",
    });
  });

  it("quest'anno va dal primo gennaio a oggi", () => {
    expect(resolvePeriodPreset("this_year", TODAY)).toEqual({
      date_from: "2026-01-01",
      date_to: "2026-08-15",
    });
  });

  it("ultimi 12 mesi va da un anno fa a oggi", () => {
    expect(resolvePeriodPreset("last_12_months", TODAY)).toEqual({
      date_from: "2025-08-15",
      date_to: "2026-08-15",
    });
  });

  it("personalizzato non risolve un range: il chiamante decide", () => {
    expect(resolvePeriodPreset("custom", TODAY)).toBeNull();
  });
});
