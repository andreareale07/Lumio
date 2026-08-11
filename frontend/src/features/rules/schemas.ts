import { z } from "zod";

import { RULE_FIELDS, RULE_OPERATORS } from "../../types/api";

function isValidRegex(pattern: string): boolean {
  try {
    new RegExp(pattern);
    return true;
  } catch {
    return false;
  }
}

// Rispecchia le validazioni di backend/app/schemas/rules.py: regex validata
// anche lato client prima dell'invio, merchant_equals richiede field=merchant.
export const ruleSchema = z
  .object({
    name: z.string().min(1, "Inserisci un nome"),
    field: z.enum(RULE_FIELDS),
    operator: z.enum(RULE_OPERATORS),
    value: z.string().min(1, "Inserisci un valore"),
    category_id: z.string().min(1, "Seleziona una categoria"),
    priority: z.number().int(),
    is_active: z.boolean(),
  })
  .superRefine((data, ctx) => {
    if (data.operator === "regex" && !isValidRegex(data.value)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["value"], message: "Espressione regolare non valida" });
    }
    if (data.operator === "merchant_equals" && data.field !== "merchant") {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["field"],
        message: "'merchant_equals' richiede il campo Merchant",
      });
    }
  });

export type RuleFormValues = z.infer<typeof ruleSchema>;

export const RULE_FIELD_LABELS: Record<(typeof RULE_FIELDS)[number], string> = {
  description: "Descrizione",
  merchant: "Merchant",
};

export const RULE_OPERATOR_LABELS: Record<(typeof RULE_OPERATORS)[number], string> = {
  equals: "è esattamente",
  contains: "contiene",
  starts_with: "inizia con",
  ends_with: "finisce con",
  regex: "corrisponde a (regex)",
  merchant_equals: "merchant è esattamente",
};
