import { describe, expect, it } from "vitest";

import { trimLeadingEmpty } from "../src/lib/trimSeries";

const isZero = (v: number) => v === 0;

describe("trimLeadingEmpty", () => {
  it("taglia i punti a zero prima del primo dato", () => {
    expect(trimLeadingEmpty([0, 0, 0, 0, 5, 0, 7], isZero)).toEqual([5, 0, 7]);
  });

  it("mantiene gli zeri successivi al primo dato", () => {
    expect(trimLeadingEmpty([0, 3, 0, 0], isZero)).toEqual([3, 0, 0]);
  });

  it("tiene almeno minPoints punti finali", () => {
    expect(trimLeadingEmpty([0, 0, 0, 0, 0, 9], isZero, 3)).toEqual([0, 0, 9]);
  });

  it("non tocca una serie senza dati o senza zeri iniziali", () => {
    expect(trimLeadingEmpty([0, 0, 0], isZero)).toEqual([0, 0, 0]);
    expect(trimLeadingEmpty([1, 0, 2], isZero)).toEqual([1, 0, 2]);
    expect(trimLeadingEmpty([], isZero)).toEqual([]);
  });
});
