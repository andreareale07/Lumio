import { useState } from "react";
import { Plus, Wand2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { useCategories } from "../categories/api";
import { useCategoryLabel } from "../categories/utils";
import { useDeleteRule, useRuleSuggestions, useRules, useUpdateRule } from "./api";
import { ReclassificationPanel } from "./ReclassificationPanel";
import { RuleFormDialog } from "./RuleFormDialog";
import { ruleFieldLabel, ruleOperatorLabel } from "./schemas";
import type { Rule } from "../../types/api";

export function RulesPage() {
  const { t } = useTranslation(["settings", "rules", "common"]);
  const categoryLabel = useCategoryLabel();
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
        <h1 className="text-lg font-semibold text-text">{t("items.rules.label")}</h1>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4" /> {t("items.rules.page.newRule")}
        </Button>
      </div>

      {suggestions && suggestions.length > 0 && (
        <div className="flex flex-col gap-2">
          {suggestions.map((s) => (
            <Card key={`${s.match_field}-${s.match_value}-${s.category_id}`} className="flex items-center justify-between gap-3 border-primary/30 bg-primary/5">
              <p className="flex items-center gap-1.5 text-sm text-text">
                <Wand2 className="h-4 w-4 text-primary" />
                {t("items.rules.page.suggestion.text", {
                  count: s.occurrences,
                  value: s.match_value,
                  category: categoryLabel(categories, s.category_id),
                })}
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
                {t("items.rules.page.suggestion.createRule")}
              </Button>
            </Card>
          ))}
        </div>
      )}

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState message={t("items.rules.page.loadError")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && rules && rules.length === 0 && (
        <EmptyState
          icon={Wand2}
          title={t("items.rules.page.empty.title")}
          description={t("items.rules.page.empty.description")}
          action={<Button onClick={openCreate}>{t("items.rules.page.empty.action")}</Button>}
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
                    {ruleFieldLabel(t, rule.field)} {ruleOperatorLabel(t, rule.operator)} "{rule.value}" →{" "}
                    {categoryLabel(categories, rule.category_id)}
                  </p>
                  <p className="text-xs text-text-muted">{t("items.rules.page.priority", { value: rule.priority })}</p>
                </div>
                <div className="flex items-center gap-2">
                  {!rule.is_active && <Badge tone="neutral">{t("items.rules.page.badgeInactive")}</Badge>}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => updateRule.mutate({ id: rule.id, is_active: !rule.is_active })}
                  >
                    {t(rule.is_active ? "items.rules.page.toggleDeactivate" : "items.rules.page.toggleActivate")}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => openEdit(rule)}>
                    {t("items.rules.page.edit")}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setRuleToDelete(rule)}>
                    {t("items.rules.page.delete")}
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

      <Dialog
        open={!!ruleToDelete}
        onClose={() => setRuleToDelete(null)}
        title={t("items.rules.page.deleteDialog.title")}
      >
        <p className="text-sm text-text-muted">
          {t("items.rules.page.deleteDialog.body", { name: ruleToDelete?.name })}
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setRuleToDelete(null)}>
            {t("common:actions.cancel")}
          </Button>
          <Button
            variant="danger"
            onClick={async () => {
              if (ruleToDelete) await deleteRule.mutateAsync(ruleToDelete.id);
              setRuleToDelete(null);
            }}
          >
            {t("items.rules.page.delete")}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
