import { describe, expect, it } from "vitest";

import {
  autoRuleName,
  conditionsToSelection,
  defaultSelection,
  normalizeConditions,
  selectionToConditions,
  tokenizeDescription,
  validateCondition,
} from "../src/features/rules/conditions";

const DESCRIPTION = "BONIFICO SEPA ISTANTANEO TRN CCTX0012345 BENEF. Reale Francesco PER Rata Mutuo";

describe("tokenizeDescription", () => {
  it("segna come variabili le parole con cifre o senza lettere", () => {
    const tokens = tokenizeDescription("TRN CCTX0012345 - 487,30 Rata");
    expect(tokens.map((token) => [token.text, token.variable])).toEqual([
      ["TRN", false],
      ["CCTX0012345", true],
      ["-", true],
      ["487,30", true],
      ["Rata", false],
    ]);
  });
});

describe("selectionToConditions", () => {
  const tokens = tokenizeDescription(DESCRIPTION);

  it("unisce le parole adiacenti in un'unica frase", () => {
    const selected = new Set([7, 8, 9]); // Francesco PER Rata? indici sotto
    const words = tokens.map((token) => token.text);
    const rata = words.indexOf("Rata");
    const mutuo = words.indexOf("Mutuo");
    const conditions = selectionToConditions(tokens, new Set([rata, mutuo]));
    expect(conditions).toEqual([{ field: "description", operator: "contains", value: "Rata Mutuo" }]);
    expect(selected.size).toBe(3);
  });

  it("una parola variabile interrompe la frase e non si può selezionare", () => {
    const words = tokens.map((token) => token.text);
    const indexes = new Set([words.indexOf("TRN"), words.indexOf("CCTX0012345"), words.indexOf("BENEF.")]);
    const conditions = selectionToConditions(tokens, indexes);
    expect(conditions.map((c) => c.value)).toEqual(["TRN", "BENEF."]);
  });

  it("ritrova le parole di una frase nella descrizione", () => {
    const selected = conditionsToSelection(tokens, [
      { field: "description", operator: "contains", value: "reale francesco" },
    ]);
    const words = tokens.map((token) => token.text);
    expect([...selected].sort((a, b) => a - b)).toEqual([words.indexOf("Reale"), words.indexOf("Francesco")]);
  });

  it("di partenza seleziona l'ultima sequenza di parole fisse", () => {
    const selected = defaultSelection(tokens);
    const conditions = selectionToConditions(tokens, selected);
    expect(conditions.map((c) => c.value)).toEqual(["BENEF. Reale Francesco PER Rata Mutuo"]);
  });
});

describe("validateCondition", () => {
  it("richiede un testo e accetta solo regex valide e corte", () => {
    expect(validateCondition({ field: "description", operator: "contains", value: " " })).toBe("value");
    expect(validateCondition({ field: "description", operator: "regex", value: "[abc" })).toBe("regex");
    expect(validateCondition({ field: "description", operator: "regex", value: "a".repeat(201) })).toBe("regexLength");
    expect(validateCondition({ field: "description", operator: "regex", value: "rata\\s+mutuo" })).toBeNull();
  });

  it("l'importo richiede almeno un estremo valido e minimo non sopra il massimo", () => {
    expect(validateCondition({ field: "amount", operator: "between", min: "", max: "" })).toBe("bounds");
    expect(validateCondition({ field: "amount", operator: "between", min: "abc", max: null })).toBe("bounds");
    expect(validateCondition({ field: "amount", operator: "between", min: "600", max: "100" })).toBe("order");
    expect(validateCondition({ field: "amount", operator: "between", min: "450,5", max: "520" })).toBeNull();
    expect(validateCondition({ field: "amount", operator: "between", min: null, max: "100" })).toBeNull();
  });
});

describe("normalizeConditions e nome automatico", () => {
  it("manda gli importi con il punto e toglie gli spazi dal testo", () => {
    const normalized = normalizeConditions([
      { field: "description", operator: "contains", value: "  Rata  " },
      { field: "amount", operator: "between", min: "450,50", max: "" },
    ]);
    expect(normalized[0]).toMatchObject({ value: "Rata" });
    expect(normalized[1]).toEqual({ field: "amount", operator: "between", min: "450.50", max: null });
  });

  it("il nome automatico è la prima frase di testo", () => {
    expect(
      autoRuleName([
        { field: "amount", operator: "between", min: "1", max: null },
        { field: "description", operator: "contains", value: "Rata Mutuo" },
      ]),
    ).toBe("Rata Mutuo");
  });
});
