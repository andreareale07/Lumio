import { describe, expect, it } from "vitest";

import {
  bucketStart,
  calculatePeriodComparison,
  migrateLegacyPeriodParams,
  nextBucketStart,
  periodForAnchor,
  periodLabel,
  previousPeriod,
  resolvePeriodPreset,
  shiftAnchor,
  slidingWindow,
} from "../src/lib/period";

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

describe("bucketStart", () => {
  it("settimana parte da lunedi', non da domenica", () => {
    const sunday = new Date(2026, 7, 16); // 16 agosto 2026 e' domenica
    expect(bucketStart("week", sunday)).toEqual(new Date(2026, 7, 10)); // lunedi' 10 agosto
  });

  it("trimestre arrotonda al mese di inizio trimestre", () => {
    expect(bucketStart("quarter", TODAY)).toEqual(new Date(2026, 6, 1)); // T3 = luglio-settembre
  });

  it("semestre riconosce la seconda meta' dell'anno", () => {
    expect(bucketStart("semester", TODAY)).toEqual(new Date(2026, 6, 1)); // agosto -> S2 (lug-dic)
    expect(bucketStart("semester", new Date(2026, 2, 1))).toEqual(new Date(2026, 0, 1)); // marzo -> S1
  });
});

describe("nextBucketStart / shiftAnchor", () => {
  it("mese: fine gennaio non causa overflow di giorno", () => {
    const jan1 = new Date(2026, 0, 1);
    expect(nextBucketStart("month", jan1)).toEqual(new Date(2026, 1, 1));
  });

  it("anno: trimestre Q4 avanza all'anno successivo", () => {
    const q4 = new Date(2026, 9, 1);
    expect(nextBucketStart("quarter", q4)).toEqual(new Date(2027, 0, 1));
  });

  it("semestre: H2 avanza a H1 dell'anno successivo", () => {
    const h2 = new Date(2026, 6, 1);
    expect(shiftAnchor("semester", h2, 1)).toEqual(new Date(2027, 0, 1));
  });

  it("settimana: indietro di 2 passi attraversa il cambio di mese", () => {
    const firstMonday = new Date(2026, 7, 3); // lunedi' 3 agosto
    expect(shiftAnchor("week", firstMonday, -2)).toEqual(new Date(2026, 6, 20)); // lunedi' 20 luglio
  });
});

describe("periodForAnchor", () => {
  it("mese: date_to e' l'ultimo giorno del mese, anche a febbraio bisestile", () => {
    expect(periodForAnchor("month", new Date(2028, 1, 10))).toEqual({
      date_from: "2028-02-01",
      date_to: "2028-02-29",
    });
  });

  it("semestre: H1 termina il 30 giugno", () => {
    expect(periodForAnchor("semester", new Date(2026, 2, 1))).toEqual({
      date_from: "2026-01-01",
      date_to: "2026-06-30",
    });
  });

  it("anno: date_to e' il 31 dicembre", () => {
    expect(periodForAnchor("year", TODAY)).toEqual({ date_from: "2026-01-01", date_to: "2026-12-31" });
  });
});

describe("slidingWindow", () => {
  it("finestra di 6 mesi che termina nel bucket di anchor", () => {
    expect(slidingWindow("month", TODAY, 6)).toEqual({ date_from: "2026-03-01", date_to: "2026-08-31" });
  });

  it("finestra di 1 unita' equivale al periodo puntuale", () => {
    expect(slidingWindow("quarter", TODAY, 1)).toEqual(periodForAnchor("quarter", TODAY));
  });
});

describe("periodLabel", () => {
  it("mese in minuscolo, coerente con la convenzione italiana", () => {
    expect(periodLabel("month", TODAY)).toBe("agosto 2026");
  });

  it("trimestre e semestre usano l'abbreviazione T/S", () => {
    expect(periodLabel("quarter", TODAY)).toBe("T3 2026");
    expect(periodLabel("semester", TODAY)).toBe("S2 2026");
  });

  it("anno e' solo il numero", () => {
    expect(periodLabel("year", TODAY)).toBe("2026");
  });
});

describe("migrateLegacyPeriodParams", () => {
  it("nessun period legacy: nulla da migrare", () => {
    expect(migrateLegacyPeriodParams(new URLSearchParams(), TODAY)).toBeNull();
  });

  it("this_month migra a granularita' mese sul mese corrente", () => {
    expect(migrateLegacyPeriodParams(new URLSearchParams("period=this_month"), TODAY)).toEqual({
      mode: "granular",
      granularity: "month",
      anchor: "2026-08-01",
    });
  });

  it("last_month migra al mese precedente", () => {
    expect(migrateLegacyPeriodParams(new URLSearchParams("period=last_month"), TODAY)).toEqual({
      mode: "granular",
      granularity: "month",
      anchor: "2026-07-01",
    });
  });

  it("last_3_months non ha equivalente granulare: migra a range personalizzato congelato", () => {
    expect(migrateLegacyPeriodParams(new URLSearchParams("period=last_3_months"), TODAY)).toEqual({
      mode: "custom",
      from: "2026-05-15",
      to: "2026-08-15",
    });
  });

  it("custom con from/to presenti li riusa direttamente", () => {
    expect(
      migrateLegacyPeriodParams(new URLSearchParams("period=custom&from=2026-01-01&to=2026-01-31"), TODAY),
    ).toEqual({ mode: "custom", from: "2026-01-01", to: "2026-01-31" });
  });
});

describe("calculatePeriodComparison", () => {
  // Rework Temporal (SPEC_FE_REDESIGN §16): logica prima duplicata in
  // KpiCard.tsx e DrillDownDrawer.tsx, ora centralizzata qui.
  it("aumento su una metrica dove salire e' un bene (es. Entrate) e' positivo", () => {
    expect(calculatePeriodComparison(120, 100, true)).toEqual({
      change: 0.2,
      trend: "up",
      isGood: true,
    });
  });

  it("aumento su una metrica dove salire e' un male (es. Spese) e' negativo", () => {
    expect(calculatePeriodComparison(120, 100, false)).toEqual({
      change: 0.2,
      trend: "up",
      isGood: false,
    });
  });

  it("diminuzione inverte trend e giudizio rispetto ad un aumento", () => {
    expect(calculatePeriodComparison(80, 100, true)).toEqual({
      change: -0.2,
      trend: "down",
      isGood: false,
    });
  });

  it("nessun valore precedente: nessun confronto possibile", () => {
    expect(calculatePeriodComparison(100, undefined, true)).toEqual({
      change: undefined,
      trend: "flat",
      isGood: null,
    });
  });

  it("valore precedente zero: confronto contro zero non e' una percentuale sensata", () => {
    expect(calculatePeriodComparison(100, 0, true)).toEqual({
      change: undefined,
      trend: "flat",
      isGood: null,
    });
  });

  it("valore invariato: variazione zero, nessun giudizio", () => {
    expect(calculatePeriodComparison(100, 100, true)).toEqual({
      change: 0,
      trend: "flat",
      isGood: null,
    });
  });
});

describe("previousPeriod", () => {
  // Speculare a `previous_period` in backend/app/services/analytics_calc.py
  // (drill-down del cruscotto: confronto per una singola categoria, dove
  // il backend non calcola gia' un valore "previous_*" come per il summary).
  it("un mese intero -> il mese precedente, stessa durata", () => {
    expect(previousPeriod("2026-08-01", "2026-08-31")).toEqual({
      date_from: "2026-07-01",
      date_to: "2026-07-31",
    });
  });

  it("un solo giorno -> il giorno immediatamente precedente", () => {
    expect(previousPeriod("2026-08-15", "2026-08-15")).toEqual({
      date_from: "2026-08-14",
      date_to: "2026-08-14",
    });
  });

  it("range arbitrario di N giorni -> gli N giorni immediatamente precedenti", () => {
    // 10 giorni (1-10 agosto compresi) -> i 10 giorni precedenti (22-31 luglio)
    expect(previousPeriod("2026-08-01", "2026-08-10")).toEqual({
      date_from: "2026-07-22",
      date_to: "2026-07-31",
    });
  });

  it("attraversa il cambio d'anno", () => {
    expect(previousPeriod("2026-01-01", "2026-01-31")).toEqual({
      date_from: "2025-12-01",
      date_to: "2025-12-31",
    });
  });
});
