import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { CategoryPicker } from "../categories/CategoryPicker";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { RULE_FIELDS, RULE_OPERATORS, type Rule } from "../../types/api";
import { useCreateRule, useUpdateRule } from "./api";
import { RULE_FIELD_LABELS, RULE_OPERATOR_LABELS, type RuleFormValues, ruleSchema } from "./schemas";

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
  const createRule = useCreateRule();
  const updateRule = useUpdateRule();
  const [formError, setFormError] = useState<string | null>(null);
  const isEditing = !!rule;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<RuleFormValues>({
    resolver: zodResolver(ruleSchema),
    defaultValues: valuesFrom(rule, defaults),
  });

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
      setFormError(friendlyErrorMessage(error, "Non è stato possibile salvare la regola."));
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={isEditing ? "Modifica regola" : "Nuova regola"}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label="Nome" error={errors.name?.message} {...register("name")} />
        <div className="grid grid-cols-2 gap-3">
          <Select label="Campo" error={errors.field?.message} {...register("field")}>
            {RULE_FIELDS.map((field) => (
              <option key={field} value={field}>
                {RULE_FIELD_LABELS[field]}
              </option>
            ))}
          </Select>
          <Select label="Operatore" error={errors.operator?.message} {...register("operator")}>
            {RULE_OPERATORS.map((operator) => (
              <option key={operator} value={operator}>
                {RULE_OPERATOR_LABELS[operator]}
              </option>
            ))}
          </Select>
        </div>
        <Input label="Valore" error={errors.value?.message} {...register("value")} />
        <CategoryPicker error={errors.category_id?.message} {...register("category_id")} />
        <Input
          label="Priorità"
          type="number"
          hint="Numero più basso = valutata prima"
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
            Annulla
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {isEditing ? "Salva" : "Crea regola"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
