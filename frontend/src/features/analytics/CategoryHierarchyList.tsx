import { useState } from "react";
import type { ComponentType } from "react";
import { ArrowUpRight, ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ChartCard } from "../../components/charts/ChartCard";
import { EmptyState } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { clickableRowArrowClasses, clickableRowClasses } from "../../lib/clickableRow";
import { formatMoney, formatPercent } from "../../lib/format";
import { isSignificantChange, median } from "../../lib/stats";
import { useCategories } from "../categories/api";
import type { AnalyticsDirection, AnalyticsGranularity, CategoryBreakdownItem } from "../../types/api";
import { useAnalyticsByCategory, useAnalyticsCategoryTrend } from "./api";

const CATEGORY_DISPLAY_LIMIT = 8;

interface CategoryHierarchyListProps {
  direction: AnalyticsDirection;
  currency: string;
  icon: ComponentType<{ className?: string }>;
  title: string;
  emptyDescription: string;
  period: { date_from: string; date_to: string };
  trendWindow: { date_from: string; date_to: string };
  granularity: AnalyticsGranularity;
  financialAccountId?: string;
  /** Maschera "mesi fantasma" allineata a `trendWindow`/`granularity" — un
   * bucket senza NESSUN dato di workspace (entrate E spese entrambe zero,
   * calcolato dal chiamante sulla stessa finestra usata qui) non deve
   * abbassare artificialmente la baseline "tipico" di una categoria. Se
   * omessa, tutti i bucket sono considerati validi. */
  ghostMask?: boolean[];
  onSelectRow: (id: string, name: string) => void;
}

/** Gerarchia categoria -> sottocategoria (redesign Spese/Entrate, FETTA 1):
 * sostituisce SIA il donut SIA la lista piatta non stilizzata di prima —
 * stessa ricerca gia' applicata alla Dashboard (un donut non si legge oltre
 * 5-6 fette, qui le categorie sono strutturalmente 15-30). Il livello
 * merchant/transazioni resta nel `DrillDownDrawer` esistente, aperto dal
 * chiamante via `onSelectRow` — questo componente si ferma ai primi due
 * livelli (categoria/sottocategoria). */
export function CategoryHierarchyList({
  direction,
  currency,
  icon,
  title,
  emptyDescription,
  period,
  trendWindow,
  granularity,
  financialAccountId,
  ghostMask,
  onSelectRow,
}: CategoryHierarchyListProps) {
  const { t } = useTranslation(["analytics"]);
  const [showAll, setShowAll] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const byCategory = useAnalyticsByCategory({
    ...period,
    direction,
    financial_account_id: financialAccountId,
  });
  const trend = useAnalyticsCategoryTrend({
    ...trendWindow,
    granularity,
    direction,
    financial_account_id: financialAccountId,
  });
  const children = useAnalyticsByCategory(
    { ...period, direction, parent_id: expandedId ?? undefined, financial_account_id: financialAccountId },
    { enabled: !!expandedId },
  );
  const categories = useCategories();

  const items = byCategory.data?.items ?? [];
  const visibleItems = showAll ? items : items.slice(0, CATEGORY_DISPLAY_LIMIT);
  const maxTotal = Math.max(1, ...items.map((i) => Number(i.total)));

  const hasChildren = new Set((categories.data ?? []).filter((c) => c.parent_id !== null).map((c) => c.parent_id));

  const trendByCategory = new Map((trend.data?.series ?? []).map((s) => [s.category_id, s.values.map(Number)]));

  // Una riga i cui movimenti sono taggati DIRETTAMENTE sul padre (nessuna
  // sottocategoria) torna dal backend con lo stesso `category_id` del padre
  // e il nome del padre stesso — rietichettata qui, non nel backend (e' un
  // dettaglio di presentazione).
  function childItems(parentId: string, items: CategoryBreakdownItem[]): CategoryBreakdownItem[] {
    return items.map((child) =>
      child.category_id === parentId ? { ...child, name: t("breakdown.hierarchy.directOnParent") } : child,
    );
  }

  // Solo lo scostamento "vs tipico" — niente piu' sparkline per riga
  // (richiesta esplicita dell'utente dopo aver visto la pagina dal vivo: i
  // grafici piccolini non aggiungevano informazione leggibile). La query
  // `trend` resta: e' la fonte di questo calcolo, non solo dello sparkline
  // rimosso.
  function categoryDeviation(categoryId: string | null): number | undefined {
    const values = trendByCategory.get(categoryId);
    if (!values || values.length < 2) return undefined;
    const mask = ghostMask ?? values.map(() => true);
    const current = values.at(-1) ?? 0;
    const priorValues = values.slice(0, -1).filter((_, i) => mask[i] !== false);
    if (priorValues.length === 0) return undefined;
    const baseline = median(priorValues);
    if (!isSignificantChange(current, baseline) || baseline === 0) return undefined;
    return (current - baseline) / Math.abs(baseline);
  }

  function renderRow(item: CategoryBreakdownItem, opts: { indented?: boolean; expandable?: boolean } = {}) {
    const { indented, expandable } = opts;
    const barPct = Math.round((Number(item.total) / maxTotal) * 100);
    const deviationPct = categoryDeviation(item.category_id);
    const isExpanded = expandedId === item.category_id;
    const isUncategorized = item.category_id === null;

    const row = (
      <>
        <div className="flex items-center justify-between gap-2 text-sm">
          <div className="flex min-w-0 items-center gap-2">
            {expandable && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setExpandedId(isExpanded ? null : item.category_id);
                }}
                aria-label={t("breakdown.hierarchy.expand")}
                aria-expanded={isExpanded}
                className="shrink-0 text-text-muted hover:text-text"
              >
                {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              </button>
            )}
            <span className="truncate text-text">{item.name}</span>
            <span className="shrink-0 text-xs text-text-muted">{Math.round(Number(item.share) * 100)}%</span>
            <span className="hidden shrink-0 text-xs text-text-muted sm:inline">
              {t("breakdown.hierarchy.transactionsCount", { count: item.transactions_count })}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {deviationPct !== undefined && (
              <span
                className={
                  deviationPct >= 0 === (direction === "income") ? "text-xs text-success" : "text-xs text-danger"
                }
              >
                {t("breakdown.hierarchy.vsTypical", { value: formatPercent(deviationPct, { signed: true }) })}
              </span>
            )}
            <span className="font-numeric text-text">{formatMoney(item.total, currency)}</span>
            {!isUncategorized && <ArrowUpRight className={clickableRowArrowClasses} aria-hidden="true" />}
          </div>
        </div>
        {!indented && (
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-hover">
            <div className="h-full rounded-full bg-primary" style={{ width: `${barPct}%` }} />
          </div>
        )}
      </>
    );

    if (isUncategorized) {
      return (
        <div key="none" className={indented ? "pl-6" : ""}>
          {row}
        </div>
      );
    }

    return (
      <button
        key={item.category_id}
        type="button"
        onClick={() => onSelectRow(item.category_id as string, item.name)}
        className={`w-full text-left ${clickableRowClasses} ${indented ? "pl-6" : ""}`}
      >
        {row}
      </button>
    );
  }

  return (
    <ChartCard
      title={title}
      empty={items.length === 0}
      emptyState={<EmptyState icon={icon} title={t("breakdown.hierarchy.emptyTitle")} description={emptyDescription} />}
      chartClassName="h-auto"
      tableCaption={t("breakdown.hierarchy.tableCaption")}
      tableHeaders={t("breakdown.hierarchy.tableHeaders", { returnObjects: true }) as string[]}
      tableRows={visibleItems.flatMap((item) => {
        const rows: (string | number)[][] = [
          [item.name, formatMoney(item.total, currency), `${Math.round(Number(item.share) * 100)}%`, item.transactions_count],
        ];
        if (item.category_id !== null && expandedId === item.category_id && children.data) {
          for (const child of childItems(item.category_id as string, children.data.items)) {
            rows.push([
              `${item.name} › ${child.name}`,
              formatMoney(child.total, currency),
              `${Math.round(Number(child.share) * 100)}%`,
              child.transactions_count,
            ]);
          }
        }
        return rows;
      })}
    >
      <div className="flex flex-col gap-3">
        {byCategory.isLoading && <Skeleton className="h-40 w-full" />}
        <ul className="flex flex-col gap-3">
          {visibleItems.map((item) => (
            <li key={item.category_id ?? "none"}>
              {renderRow(item, { expandable: !isUncategorizedId(item.category_id) && hasChildren.has(item.category_id) })}
              {item.category_id !== null && expandedId === item.category_id && (
                <div className="mt-2 flex flex-col gap-2">
                  {children.isLoading && <Skeleton className="h-10 w-full" />}
                  {children.data &&
                    childItems(item.category_id as string, children.data.items).map((child) => (
                      <div key={child.category_id ?? "none"}>{renderRow(child, { indented: true })}</div>
                    ))}
                </div>
              )}
            </li>
          ))}
        </ul>
        {items.length > CATEGORY_DISPLAY_LIMIT && (
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="self-start text-sm font-medium text-primary hover:underline"
          >
            {showAll ? t("breakdown.hierarchy.showLess") : t("breakdown.hierarchy.showAll")}
          </button>
        )}
      </div>
    </ChartCard>
  );
}

function isUncategorizedId(id: string | null): boolean {
  return id === null;
}
