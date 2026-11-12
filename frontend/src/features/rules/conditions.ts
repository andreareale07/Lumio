import type { AmountCondition, RuleCondition, TextCondition } from "../../types/api";

export const MAX_CONDITIONS = 10;
export const MAX_REGEX_LENGTH = 200;

/** Una parola della descrizione di un movimento. `variable` = contiene cifre o
 * non ha lettere (riferimenti, importi, date): cambia a ogni movimento e non
 * ha senso in una regola. */
export interface DescriptionToken {
  text: string;
  variable: boolean;
}

export function tokenizeDescription(description: string): DescriptionToken[] {
  return description
    .split(/\s+/)
    .filter(Boolean)
    .map((text) => ({ text, variable: /\d/.test(text) || !/\p{L}/u.test(text) }));
}

/** Parole selezionate -> condizioni "contiene": le parole selezionate e
 * adiacenti formano un'unica frase (una parola variabile la interrompe). */
export function selectionToConditions(tokens: DescriptionToken[], selected: ReadonlySet<number>): TextCondition[] {
  const phrases: string[] = [];
  let current: string[] = [];
  tokens.forEach((token, index) => {
    if (selected.has(index) && !token.variable) {
      current.push(token.text);
      return;
    }
    if (current.length > 0) phrases.push(current.join(" "));
    current = [];
  });
  if (current.length > 0) phrases.push(current.join(" "));
  return phrases.map((value) => ({ field: "description", operator: "contains", value }));
}

/** Inverso di `selectionToConditions`: ritrova le parole di ogni frase
 * "contiene" nella descrizione (utile per partire da un suggerimento). */
export function conditionsToSelection(tokens: DescriptionToken[], conditions: RuleCondition[]): Set<number> {
  const selected = new Set<number>();
  const lowered = tokens.map((token) => token.text.toLowerCase());
  for (const condition of conditions) {
    if (condition.field !== "description" || condition.operator !== "contains") continue;
    const words = condition.value.toLowerCase().split(/\s+/).filter(Boolean);
    if (words.length === 0) continue;
    for (let start = 0; start + words.length <= lowered.length; start += 1) {
      if (words.every((word, offset) => lowered[start + offset] === word)) {
        words.forEach((_, offset) => selected.add(start + offset));
        break;
      }
    }
  }
  return selected;
}

/** Selezione di partenza quando non c'e' un suggerimento: l'ultima sequenza di
 * parole fisse (nei bonifici e' di solito la causale). */
export function defaultSelection(tokens: DescriptionToken[]): Set<number> {
  const selected = new Set<number>();
  let end = tokens.length - 1;
  while (end >= 0 && tokens[end].variable) end -= 1;
  for (let index = end; index >= 0 && !tokens[index].variable; index -= 1) selected.add(index);
  return selected;
}

export function stableTokenIndexes(tokens: DescriptionToken[]): number[] {
  return tokens.flatMap((token, index) => (token.variable ? [] : [index]));
}

export function emptyTextCondition(): TextCondition {
  return { field: "description", operator: "contains", value: "" };
}

export function emptyAmountCondition(): AmountCondition {
  return { field: "amount", operator: "between", min: "", max: "" };
}

export type ConditionError = "value" | "regex" | "regexLength" | "bounds" | "order";

function parseAmount(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const value = Number(raw.replace(",", "."));
  return Number.isFinite(value) ? value : Number.NaN;
}

export function validateCondition(condition: RuleCondition): ConditionError | null {
  if (condition.field === "amount") {
    const min = parseAmount(condition.min);
    const max = parseAmount(condition.max);
    if ((min === null && max === null) || Number.isNaN(min) || Number.isNaN(max) || (min ?? 0) < 0 || (max ?? 0) < 0) {
      return "bounds";
    }
    if (min !== null && max !== null && min > max) return "order";
    return null;
  }
  if (condition.value.trim() === "") return "value";
  if (condition.operator === "regex") {
    if (condition.value.length > MAX_REGEX_LENGTH) return "regexLength";
    try {
      new RegExp(condition.value);
    } catch {
      return "regex";
    }
  }
  return null;
}

/** Condizioni pronte per il backend: importi come stringa decimale con il punto. */
export function normalizeConditions(conditions: RuleCondition[]): RuleCondition[] {
  return conditions.map((condition) => {
    if (condition.field !== "amount") return { ...condition, value: condition.value.trim() };
    const clean = (raw: string | null) => (raw === null || raw.trim() === "" ? null : raw.trim().replace(",", "."));
    return { ...condition, min: clean(condition.min), max: clean(condition.max) };
  });
}

export function hasInvalidCondition(conditions: RuleCondition[]): boolean {
  return conditions.length === 0 || conditions.some((condition) => validateCondition(condition) !== null);
}

/** Nome automatico: la prima frase di testo (o "Importo") — l'utente non deve
 * inventare un nome per ogni regola. */
export function autoRuleName(conditions: RuleCondition[]): string {
  const text = conditions.find((condition): condition is TextCondition => condition.field !== "amount");
  return (text?.value ?? "Importo").trim().slice(0, 100);
}
