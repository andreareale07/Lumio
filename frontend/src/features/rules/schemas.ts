import { z } from "zod";
import type { TFunction } from "i18next";

import { RULE_FIELDS, RULE_OPERATORS, type RuleField, type RuleOperator } from "../../types/api";

function isValidRegex(pattern: string): boolean {
  try {
    new RegExp(pattern);
    return true;
  } catch {
    return false;
  }
}

/** Etichette campo/operatore: namespace "enums" (SPEC_FE_REDESIGN §27),
 * stesso pattern di `useTransactionTypeLabel`/`aiProviderLabel`. */
export function ruleFieldLabel(t: TFunction, field: RuleField): string {
  return t(`enums:ruleField.${field}`);
}

export function ruleOperatorLabel(t: TFunction, operator: RuleOperator): string {
  return t(`enums:ruleOperator.${operator}`);
}

// Rispecchia le validazioni di backend/app/schemas/rules.py: regex validata
// anche lato client prima dell'invio, merchant_equals richiede field=merchant.
export function buildRuleSchema(t: TFunction) {
  return z
    .object({
      name: z.string().min(1, t("rules:validation.name")),
      field: z.enum(RULE_FIELDS),
      operator: z.enum(RULE_OPERATORS),
      value: z.string().min(1, t("rules:validation.value")),
      category_id: z.string().min(1, t("rules:validation.category")),
      priority: z.number().int(),
      is_active: z.boolean(),
    })
    .superRefine((data, ctx) => {
      if (data.operator === "regex" && !isValidRegex(data.value)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["value"], message: t("rules:validation.invalidRegex") });
      }
      if (data.operator === "merchant_equals" && data.field !== "merchant") {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["field"],
          message: t("rules:validation.merchantEqualsRequiresMerchant"),
        });
      }
    });
}

export type RuleFormValues = z.infer<ReturnType<typeof buildRuleSchema>>;
