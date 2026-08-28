import { describe, expect, it } from "vitest";

import { mean, median } from "../src/lib/stats";

describe("mean", () => {
  it("media aritmetica di valori dispari", () => {
    expect(mean([1, 2, 3])).toBeCloseTo(2, 10);
  });

  it("media aritmetica di valori pari", () => {
    expect(mean([1, 2, 3, 4])).toBeCloseTo(2.5, 10);
  });

  it("array vuoto -> 0, mai NaN", () => {
    expect(mean([])).toBe(0);
  });
});

describe("median", () => {
  it("mediana con numero dispari di valori", () => {
    expect(median([5, 1, 3])).toBe(3);
  });

  it("mediana con numero pari di valori (media dei due centrali)", () => {
    expect(median([1, 2, 3, 4])).toBeCloseTo(2.5, 10);
  });

  it("array vuoto -> 0, mai NaN", () => {
    expect(median([])).toBe(0);
  });

  it("non muta l'array originale", () => {
    const values = [3, 1, 2];
    median(values);
    expect(values).toEqual([3, 1, 2]);
  });
});
