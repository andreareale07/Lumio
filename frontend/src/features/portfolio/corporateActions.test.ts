import { describe, expect, it } from "vitest";

import { ratioToUnits } from "./corporateActions";

describe("ratioToUnits", () => {
  it("converte un raggruppamento 10.000:1", () => {
    expect(ratioToUnits("0.0001")).toEqual({ oldUnits: "10000", newUnits: "1" });
  });

  it("converte un frazionamento 1:4", () => {
    expect(ratioToUnits("4")).toEqual({ oldUnits: "1", newUnits: "4" });
  });

  it("ricade su 1:1 per un rapporto non valido", () => {
    expect(ratioToUnits("abc")).toEqual({ oldUnits: "1", newUnits: "1" });
    expect(ratioToUnits("0")).toEqual({ oldUnits: "1", newUnits: "1" });
  });
});
