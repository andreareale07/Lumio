import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useController, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { CategoryPicker } from "../categories/CategoryPicker";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { RULE_FIELDS, RULE_OPERATORS, type Rule } from "../../types/api";
import { useCreateRule, useUpdateRule } from "./api";
import { buildRuleSchema, ruleFieldLabel, ruleOperatorLabel, type RuleFormValues } from "./schemas";

export interface RuleDialogDefaults {
  name?: string;
  field?: RuleFormValues["field"];
  operator?: RuleFormValues["operator"];
  value?: string;
  category_id?: string;
}

interface RuleFormDialogProps {
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
  /** Se presente, il dialog modifica questa regola invece di crearne una nuova. */
  rule?: Rule | null;
  defaults?: RuleDialogDefaults;
}

function valuesFrom(rule: Rule | null | undefined, defaults: RuleDialogDefaults | undefined): RuleFormValues {
  if (rule) {
    return {
      name: rule.name,
      field: rule.field,
      operator: rule.operator,
      value: rule.value,
      category_id: rule.category_id,
      priority: rule.priority,
      is_active: rule.is_active,
    };
  }
  return {
    name: defaults?.name ?? "",
    field: defaults?.field ?? "description",
    operator: defaults?.operator ?? "contains",
    value: defaults?.value ?? "",
    category_id: defaults?.category_id ?? "",
    priority: 100,
    is_active: true,
  };
}

export function RuleFormDialog({ open, onClose, onSaved, rule, defaults }: RuleFormDialogProps) {
  const { t } = useTranslation(["rules", "common"]);
  const createRule = useCreateRule();
  const updateRule = useUpdateRule();
  const [formError, setFormError] = useState<string | null>(null);
  const isEditing = !!rule;

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors, isSubmitting },
  } = useForm<RuleFormValues>({
    resolver: zodResolver(buildRuleSchema(t)),
    defaultValues: valuesFrom(rule, defaults),
  });
  // CategoryPicker e' un componente controllato (si aspetta `value` come
  // prop esplicita) — a differenza degli <input>/<select> nativi sopra,
  // spread di register() qui non basta: register() passa solo onChange/
  // onBlur/name/ref, mai `value`, quindi il campo risultava sempre vuoto
  // (bug reale: "categoria sbiancata" aprendo il dialog da una
  // transazione, ma capitava anche in modifica di una regola esistente).
  const categoryField = useController({ name: "category_id", control });

  useEffect(() => {
    if (open) {
      reset(valuesFrom(rule, defaults));
      setFormError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo su open/rule/defaults
  }, [open, rule, defaults]);

  const onSubmit = async (values: RuleFormValues) => {
    setFormError(null);
    try {
      if (isEditing) {
        await updateRule.mutateAsync({ id: rule.id, ...values });
      } else {
        await createRule.mutateAsync(values);
      }
      onSaved?.();
      onClose();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("dialog.error")));
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={isEditing ? t("dialog.editTitle") : t("dialog.createTitle")}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label={t("fields.name")} error={errors.name?.message} {...register("name")} />
        <div className="grid grid-cols-2 gap-3">
          <Select label={t("fields.field")} error={errors.field?.message} {...register("field")}>
            {RULE_FIELDS.map((field) => (
              <option key={field} value={field}>
                {ruleFieldLabel(t, field)}
              </option>
            ))}
          </Select>
          <Select label={t("fields.operator")} error={errors.operator?.message} {...register("operator")}>
            {RULE_OPERATORS.map((operator) => (
              <option key={operator} value={operator}>
                {ruleOperatorLabel(t, operator)}
              </option>
            ))}
          </Select>
        </div>
        <Input label={t("fields.value")} error={errors.value?.message} {...register("value")} />
        <CategoryPicker
          error={errors.category_id?.message}
          value={categoryField.field.value}
          onChange={categoryField.field.onChange}
          onBlur={categoryField.field.onBlur}
          name={categoryField.field.name}
          ref={categoryField.field.ref}
        />
        <Input
          label={t("fields.priority")}
          type="number"
          hint={t("priorityHint")}
          error={errors.priority?.message}
          {...register("priority", { valueAsNumber: true })}
        />
        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}
        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t("common:actions.cancel")}
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {isEditing ? t("dialog.submitEdit") : t("dialog.submitCreate")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
