import { useState } from "react";
import { Plus, Wand2 } from "lucide-react";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { useCategories } from "../categories/api";
import { categoryLabel } from "../categories/utils";
import { useDeleteRule, useRuleSuggestions, useRules, useUpdateRule } from "./api";
import { ReclassificationPanel } from "./ReclassificationPanel";
import { RuleFormDialog } from "./RuleFormDialog";
import { RULE_FIELD_LABELS, RULE_OPERATOR_LABELS } from "./schemas";
import type { Rule } from "../../types/api";

export function RulesPage() {
  const { data: rules, isLoading, isError, refetch } = useRules();
  const { data: categories } = useCategories();
  const { data: suggestions } = useRuleSuggestions();
  const updateRule = useUpdateRule();
  const deleteRule = useDeleteRule();

  const [formOpen, setFormOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<Rule | null>(null);
  const [ruleToDelete, setRuleToDelete] = useState<Rule | null>(null);
  const [suggestionPrefill, setSuggestionPrefill] = useState<
    { name: string; field: "description" | "merchant"; operator: "contains" | "merchant_equals"; value: string; category_id: string }
    | null
  >(null);

  const openCreate = () => {
    setEditingRule(null);
    setFormOpen(true);
  };
  const openEdit = (rule: Rule) => {
    setEditingRule(rule);
    setFormOpen(true);
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text">Regole</h1>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4" /> Nuova regola
        </Button>
      </div>

      {suggestions && suggestions.length > 0 && (
        <div className="flex flex-col gap-2">
          {suggestions.map((s) => (
            <Card key={`${s.match_field}-${s.match_value}-${s.category_id}`} className="flex items-center justify-between gap-3 border-primary/30 bg-primary/5">
              <p className="flex items-center gap-1.5 text-sm text-text">
                <Wand2 className="h-4 w-4 text-primary" />
                Hai classificato "{s.match_value}" come {categoryLabel(categories, s.category_id)}{" "}
                {s.occurrences} volte. Vuoi creare una regola automatica?
              </p>
              <Button
                size="sm"
                onClick={() =>
                  setSuggestionPrefill({
                    name: s.match_value,
                    field: s.match_field,
                    operator: s.match_field === "merchant" ? "merchant_equals" : "contains",
                    value: s.match_value,
                    category_id: s.category_id,
                  })
                }
              >
                Crea regola
              </Button>
            </Card>
          ))}
        </div>
      )}

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState message="Non siamo riusciti a caricare le regole." onRetry={() => void refetch()} />}

      {!isLoading && !isError && rules && rules.length === 0 && (
        <EmptyState
          icon={Wand2}
          title="Nessuna regola"
          description="Crea una regola per classificare automaticamente i movimenti futuri, ad esempio NETFLIX → Abbonamenti."
          action={<Button onClick={openCreate}>Nuova regola</Button>}
        />
      )}

      {!isLoading && !isError && rules && rules.length > 0 && (
        <div className="flex flex-col gap-2">
          {rules
            .slice()
            .sort((a, b) => a.priority - b.priority)
            .map((rule) => (
              <Card key={rule.id} className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-text">{rule.name}</p>
                  <p className="text-sm text-text-muted">
                    {RULE_FIELD_LABELS[rule.field]} {RULE_OPERATOR_LABELS[rule.operator]} "{rule.value}" →{" "}
                    {categoryLabel(categories, rule.category_id)}
                  </p>
                  <p className="text-xs text-text-muted">Priorità {rule.priority}</p>
                </div>
                <div className="flex items-center gap-2">
                  {!rule.is_active && <Badge tone="neutral">Disattiva</Badge>}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => updateRule.mutate({ id: rule.id, is_active: !rule.is_active })}
                  >
                    {rule.is_active ? "Disattiva" : "Attiva"}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => openEdit(rule)}>
                    Modifica
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setRuleToDelete(rule)}>
                    Elimina
                  </Button>
                </div>
              </Card>
            ))}
        </div>
      )}

      <ReclassificationPanel />

      <RuleFormDialog
        open={formOpen || !!suggestionPrefill}
        onClose={() => {
          setFormOpen(false);
          setSuggestionPrefill(null);
        }}
        rule={editingRule}
        defaults={suggestionPrefill ?? undefined}
      />

      <Dialog open={!!ruleToDelete} onClose={() => setRuleToDelete(null)} title="Eliminare la regola?">
        <p className="text-sm text-text-muted">
          "{ruleToDelete?.name}" non classificherà più le nuove transazioni. Le transazioni già classificate non
          vengono modificate.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setRuleToDelete(null)}>
            Annulla
          </Button>
          <Button
            variant="danger"
            onClick={async () => {
              if (ruleToDelete) await deleteRule.mutateAsync(ruleToDelete.id);
              setRuleToDelete(null);
            }}
          >
            Elimina
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
