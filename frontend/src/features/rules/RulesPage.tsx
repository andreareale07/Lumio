import { useMemo, useState } from "react";
import { Plus, Wand2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { FilterBar, type SelectFilter } from "../../components/filters/FilterBar";
import { usePageToolbar } from "../../components/layout/PageToolbarContext";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Pagination } from "../../components/ui/Pagination";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { usePagedList } from "../../lib/usePagedList";
import { useUrlListFilters } from "../../lib/useUrlListFilters";
import { useCategories } from "../categories/api";
import { useCategoryLabel } from "../categories/utils";
import { useDeleteRule, useRuleSuggestions, useRules, useUpdateRule } from "./api";
import { ReclassificationBanner } from "./ReclassificationBanner";
import { ReclassificationDialog } from "./ReclassificationDialog";
import { RuleBuilderDialog, type RuleBuilderDefaults } from "./RuleBuilderDialog";
import { RuleSentence } from "./RuleSentence";
import { RuleSuggestionCard } from "./RuleSuggestionCard";
import { useReclassificationLive } from "./useReclassificationLive";
import type { Rule } from "../../types/api";

const PAGE_SIZE = 12;
const SUGGESTIONS_COLLAPSED = 3;

type StatusValue = "active" | "inactive";

export function RulesPage() {
  const { t } = useTranslation(["settings", "rules", "common"]);
  const categoryLabel = useCategoryLabel();
  const { data: rules, isLoading, isError, refetch } = useRules();
  const { data: categories } = useCategories();
  const { data: suggestions } = useRuleSuggestions();
  const updateRule = useUpdateRule();
  const deleteRule = useDeleteRule();
  const live = useReclassificationLive();

  const [builder, setBuilder] = useState<{ rule: Rule | null; defaults?: RuleBuilderDefaults } | null>(null);
  const [ruleToDelete, setRuleToDelete] = useState<Rule | null>(null);
  const [reclassOpen, setReclassOpen] = useState(false);
  const [showAllSuggestions, setShowAllSuggestions] = useState(false);
  // Ricerca e stato nell'URL (`?q=`, `?status=active`), stessa barra filtri di Movimenti.
  const { query, setQuery, getValues, setValues, clearAll, hasAnyFilter: hasFilters } = useUrlListFilters(["status"]);
  const statusValues = getValues("status").filter((value): value is StatusValue => value === "active" || value === "inactive");
  const selectFilters: SelectFilter[] = [
    {
      key: "status",
      label: t("items.rules.page.filter.label"),
      values: statusValues,
      options: [
        { value: "active", label: t("items.rules.page.filter.active") },
        { value: "inactive", label: t("items.rules.page.filter.inactive") },
      ],
    },
  ];

  const openCreate = () => setBuilder({ rule: null });
  const openEdit = (rule: Rule) => setBuilder({ rule });

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (rules ?? [])
      // Nessuno stato scelto (o entrambi) = tutte le regole.
      .filter((rule) => statusValues.length === 0 || statusValues.includes(rule.is_active ? "active" : "inactive"))
      .filter(
        (rule) =>
          needle === "" ||
          rule.name.toLowerCase().includes(needle) ||
          rule.conditions.some((c) => c.field !== "amount" && c.value.toLowerCase().includes(needle)) ||
          categoryLabel(categories, rule.category_id).toLowerCase().includes(needle),
      )
      .sort((a, b) => a.priority - b.priority || a.name.localeCompare(b.name));
  }, [rules, query, statusValues.join(","), categories, categoryLabel]);

  const paged = usePagedList(filtered, PAGE_SIZE, `${query}|${statusValues.join(",")}`);
  const activeCount = (rules ?? []).filter((rule) => rule.is_active).length;

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
          {visibleSuggestions.map((suggestion) => (
            <RuleSuggestionCard
              key={`${suggestion.category_id}-${suggestion.label}`}
              suggestion={suggestion}
              onCreate={(defaults) => setBuilder({ rule: null, defaults })}
            />
          ))}
          {hiddenSuggestions > 0 && (
            <Button variant="ghost" size="sm" className="self-start" onClick={() => setShowAllSuggestions((value) => !value)}>
              {showAllSuggestions
                ? t("rules:suggestions.showFewer")
                : t("rules:suggestions.showMore", { count: hiddenSuggestions })}
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
          <FilterBar
            search={{
              id: "rules-search",
              label: t("items.rules.page.search.label"),
              placeholder: t("items.rules.page.search.placeholder", { count: rules.length }),
              value: query,
              onChange: setQuery,
            }}
            selectFilters={selectFilters}
            onSetFilterValues={setValues}
            hasAnyFilter={hasFilters}
            onClearAll={clearAll}
          />

          {filtered.length === 0 ? (
            <div className="flex flex-col items-start gap-2 rounded-lg border border-border p-4">
              <p className="text-sm text-text-muted">{t("items.rules.page.noResults")}</p>
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
                    <RuleSentence
                      conditions={rule.conditions}
                      matchMode={rule.match_mode}
                      categoryName={categoryLabel(categories, rule.category_id)}
                      className="line-clamp-3 !text-text-muted"
                    />
                    {rule.priority !== 100 && (
                      <p className="text-xs text-text-muted">{t("items.rules.page.priority", { value: rule.priority })}</p>
                    )}
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

      <RuleBuilderDialog
        open={!!builder}
        onClose={() => setBuilder(null)}
        rule={builder?.rule ?? null}
        defaults={builder?.defaults}
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
