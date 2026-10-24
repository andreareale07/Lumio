import { useMemo, useState } from "react";
import { Plus, Search, Wand2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { usePageToolbar } from "../../components/layout/PageToolbarContext";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Pagination } from "../../components/ui/Pagination";
import { Select } from "../../components/ui/Select";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { usePagedList } from "../../lib/usePagedList";
import { useCategories } from "../categories/api";
import { useCategoryLabel } from "../categories/utils";
import { useDeleteRule, useRuleSuggestions, useRules, useUpdateRule } from "./api";
import { ReclassificationBanner } from "./ReclassificationBanner";
import { ReclassificationDialog } from "./ReclassificationDialog";
import { RuleFormDialog } from "./RuleFormDialog";
import { ruleFieldLabel, ruleOperatorLabel } from "./schemas";
import { useReclassificationLive } from "./useReclassificationLive";
import type { Rule } from "../../types/api";

const PAGE_SIZE = 12;
const SUGGESTIONS_COLLAPSED = 3;

type StatusFilter = "all" | "active" | "inactive";

export function RulesPage() {
  const { t } = useTranslation(["settings", "rules", "common"]);
  const categoryLabel = useCategoryLabel();
  const { data: rules, isLoading, isError, refetch } = useRules();
  const { data: categories } = useCategories();
  const { data: suggestions } = useRuleSuggestions();
  const updateRule = useUpdateRule();
  const deleteRule = useDeleteRule();
  const live = useReclassificationLive();

  const [formOpen, setFormOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<Rule | null>(null);
  const [ruleToDelete, setRuleToDelete] = useState<Rule | null>(null);
  const [reclassOpen, setReclassOpen] = useState(false);
  const [showAllSuggestions, setShowAllSuggestions] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
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

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (rules ?? [])
      .filter((rule) => (status === "all" ? true : status === "active" ? rule.is_active : !rule.is_active))
      .filter(
        (rule) =>
          needle === "" ||
          rule.name.toLowerCase().includes(needle) ||
          rule.value.toLowerCase().includes(needle) ||
          categoryLabel(categories, rule.category_id).toLowerCase().includes(needle),
      )
      .sort((a, b) => a.priority - b.priority || a.name.localeCompare(b.name));
  }, [rules, query, status, categories, categoryLabel]);

  const paged = usePagedList(filtered, PAGE_SIZE, `${query}|${status}`);
  const activeCount = (rules ?? []).filter((rule) => rule.is_active).length;
  const hasFilters = query.trim() !== "" || status !== "all";

  const reclassifyButton = (
    <Button variant="secondary" size="sm" onClick={() => setReclassOpen(true)}>
      <Wand2 className="h-4 w-4" /> {t("items.rules.page.reclassification.title")}
    </Button>
  );
  const newRuleButton = (
    <Button size="sm" onClick={openCreate}>
      <Plus className="h-4 w-4" /> {t("items.rules.page.newRule")}
    </Button>
  );
  const toolbarPortal = usePageToolbar(
    <>
      {reclassifyButton}
      {newRuleButton}
    </>,
  );

  const visibleSuggestions = showAllSuggestions ? (suggestions ?? []) : (suggestions ?? []).slice(0, SUGGESTIONS_COLLAPSED);
  const hiddenSuggestions = (suggestions?.length ?? 0) - SUGGESTIONS_COLLAPSED;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      {toolbarPortal}
      <div>
        <h1 className="text-lg font-semibold text-text">{t("items.rules.label")}</h1>
        {rules && rules.length > 0 && (
          <p className="text-sm text-text-muted">
            {t("items.rules.page.summary", { count: rules.length, active: activeCount })}
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-2 md:hidden">
        {reclassifyButton}
        {newRuleButton}
      </div>

      <ReclassificationBanner live={live} />

      {suggestions && suggestions.length > 0 && (
        <div className="flex flex-col gap-2">
          {visibleSuggestions.map((s) => (
            <Card key={`${s.match_field}-${s.match_value}-${s.category_id}`} className="flex items-center justify-between gap-3 border-primary/30 bg-primary/5">
              <p className="flex items-center gap-1.5 text-sm text-text">
                <Wand2 className="h-4 w-4 shrink-0 text-primary" />
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
          {hiddenSuggestions > 0 && (
            <Button variant="ghost" size="sm" className="self-start" onClick={() => setShowAllSuggestions((value) => !value)}>
              {showAllSuggestions
                ? t("items.rules.page.suggestion.showFewer")
                : t("items.rules.page.suggestion.showMore", { count: hiddenSuggestions })}
            </Button>
          )}
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
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="relative min-w-52 flex-1">
              <label htmlFor="rules-search" className="sr-only">
                {t("items.rules.page.search.label")}
              </label>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" aria-hidden="true" />
              <input
                id="rules-search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t("items.rules.page.search.placeholder", { count: rules.length })}
                className="w-full rounded-lg border border-border bg-surface py-2 pl-9 pr-3 text-sm text-text placeholder:text-text-muted"
              />
            </div>
            <div className="w-44">
              <Select
                label={t("items.rules.page.filter.label")}
                value={status}
                onChange={(event) => setStatus(event.target.value as StatusFilter)}
              >
                <option value="all">{t("items.rules.page.filter.all")}</option>
                <option value="active">{t("items.rules.page.filter.active")}</option>
                <option value="inactive">{t("items.rules.page.filter.inactive")}</option>
              </Select>
            </div>
          </div>

          {filtered.length === 0 ? (
            <div className="flex flex-col items-start gap-2 rounded-lg border border-border p-4">
              <p className="text-sm text-text-muted">{t("items.rules.page.noResults")}</p>
              {hasFilters && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setQuery("");
                    setStatus("all");
                  }}
                >
                  {t("items.rules.page.clearFilters")}
                </Button>
              )}
            </div>
          ) : (
            <ul className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface">
              {paged.pageItems.map((rule) => (
                <li
                  key={rule.id}
                  className={`flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4 ${
                    rule.is_active ? "" : "opacity-70"
                  }`}
                >
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-medium text-text">
                      <span className="truncate">{rule.name}</span>
                      {!rule.is_active && <Badge tone="neutral">{t("items.rules.page.badgeInactive")}</Badge>}
                    </p>
                    <p className="line-clamp-2 text-sm text-text-muted">
                      {ruleFieldLabel(t, rule.field)} {ruleOperatorLabel(t, rule.operator)} "{rule.value}" →{" "}
                      {categoryLabel(categories, rule.category_id)}
                    </p>
                    <p className="text-xs text-text-muted">{t("items.rules.page.priority", { value: rule.priority })}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
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
                </li>
              ))}
            </ul>
          )}

          <Pagination
            page={paged.page}
            pageCount={paged.pageCount}
            from={paged.from}
            to={paged.to}
            total={paged.total}
            onPageChange={paged.setPage}
          />
        </section>
      )}

      <ReclassificationDialog open={reclassOpen} onClose={() => setReclassOpen(false)} live={live} />

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
