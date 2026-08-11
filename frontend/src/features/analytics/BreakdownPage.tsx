import { useState } from "react";
import type { ComponentType } from "react";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DonutChart } from "../../components/charts/DonutChart";
import { PeriodFilter } from "../../components/filters/PeriodFilter";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatMoney, formatPercent, formatPeriodLabel } from "../../lib/format";
import { usePeriodFilter } from "../../lib/usePeriodFilter";
import type { AnalyticsDirection } from "../../types/api";
import { useAnalyticsByCategory, useAnalyticsByMerchant, useAnalyticsCashFlow, useAnalyticsSummary } from "./api";
import { formatBucketLabel } from "./chartData";

interface BreakdownPageProps {
  direction: AnalyticsDirection;
  title: string;
  icon: ComponentType<{ className?: string }>;
  emptyDescription: string;
}

/** Base condivisa di `/expenses` e `/income` (SPEC_FE §27-31): stessa
 * struttura — totale + variazione, andamento, categorie con drill-down per
 * merchant, top merchant — cambia solo `direction` e le etichette. */
export function BreakdownPage({ direction, title, icon, emptyDescription }: BreakdownPageProps) {
  const { dateFrom, dateTo } = usePeriodFilter();
  const period = { date_from: dateFrom, date_to: dateTo };
  const [expandedCategoryId, setExpandedCategoryId] = useState<string | null>(null);

  const summary = useAnalyticsSummary(period);
  const cashFlow = useAnalyticsCashFlow({ ...period, granularity: "month" });
  const byCategory = useAnalyticsByCategory({ ...period, direction });
  const byMerchant = useAnalyticsByMerchant({ ...period, direction });
  const categoryMerchants = useAnalyticsByMerchant(
    { ...period, direction, category_id: expandedCategoryId ?? undefined },
    { enabled: !!expandedCategoryId },
  );

  const currency = summary.data?.currency ?? "EUR";
  const totalValue = direction === "expense" ? summary.data?.expenses : summary.data?.income;
  const previousValue = direction === "expense" ? summary.data?.previous_expenses : summary.data?.previous_income;
  const change =
    totalValue !== undefined && previousValue !== undefined && Number(previousValue) !== 0
      ? (Number(totalValue) - Number(previousValue)) / Math.abs(Number(previousValue))
      : undefined;
  const isIncrease = change !== undefined && change > 0;
  const isGoodChange = change === undefined || change === 0 ? null : direction === "expense" ? !isIncrease : isIncrease;

  const granularity = cashFlow.data?.granularity ?? "month";
  const trendPoints = (cashFlow.data?.points ?? []).map((p) => ({
    period: p.period,
    label: formatBucketLabel(p.period, granularity),
    value: Number(direction === "expense" ? p.expenses : p.income),
  }));

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">{title}</h1>
          {summary.data && totalValue !== undefined && (
            <div className="flex items-baseline gap-2">
              <span className="font-numeric text-2xl font-semibold text-text">
                {formatMoney(totalValue, currency)}
              </span>
              {change !== undefined && change !== 0 && (
                <span className={`text-sm ${isGoodChange ? "text-success" : "text-danger"}`}>
                  {formatPercent(change, { signed: true })} vs periodo precedente
                </span>
              )}
            </div>
          )}
        </div>
        <PeriodFilter />
      </div>

      {summary.isError && <ErrorState message="Dati non disponibili." onRetry={() => void summary.refetch()} />}

      {cashFlow.isLoading && <Skeleton className="h-64 w-full" />}
      {cashFlow.data && (
        <ChartCard
          title="Andamento"
          subtitle={formatPeriodLabel(cashFlow.data.period.date_from, cashFlow.data.period.date_to)}
          empty={trendPoints.every((p) => p.value === 0)}
          emptyState={<EmptyState icon={icon} title="Nessun dato" description={emptyDescription} />}
          tableCaption="Andamento mensile"
          tableHeaders={["Periodo", "Totale"]}
          tableRows={trendPoints.map((p) => [p.label, formatMoney(p.value, currency)])}
        >
          <AreaTrendChart data={trendPoints} currency={currency} />
        </ChartCard>
      )}

      {byCategory.isLoading && <Skeleton className="h-64 w-full" />}
      {byCategory.data && (
        <ChartCard
          title="Categorie"
          empty={byCategory.data.items.length === 0}
          emptyState={<EmptyState icon={icon} title="Nessuna categoria" description={emptyDescription} />}
          tableCaption="Per categoria"
          tableHeaders={["Categoria", "Totale", "Quota"]}
          tableRows={byCategory.data.items.map((item) => [
            item.name,
            formatMoney(item.total, currency),
            `${Math.round(Number(item.share) * 100)}%`,
          ])}
        >
          <DonutChart
            currency={currency}
            data={byCategory.data.items.map((item) => ({ label: item.name, value: Number(item.total) }))}
          />
        </ChartCard>
      )}

      {byCategory.data && byCategory.data.items.length > 0 && (
        <ul className="flex flex-col gap-1">
          {byCategory.data.items.map((item) => {
            const categoryId = item.category_id;
            const isExpanded = categoryId !== null && expandedCategoryId === categoryId;
            return (
              <li key={categoryId ?? item.name} className="rounded-lg border border-border">
                {categoryId === null ? (
                  <div className="flex items-center justify-between p-3 text-sm">
                    <span className="text-text">{item.name}</span>
                    <span className="font-numeric text-text-muted">{formatMoney(item.total, currency)}</span>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setExpandedCategoryId(isExpanded ? null : categoryId)}
                    aria-expanded={isExpanded}
                    className="flex w-full items-center justify-between p-3 text-left text-sm hover:bg-surface-hover"
                  >
                    <span className="text-text">{item.name}</span>
                    <span className="font-numeric text-text-muted">{formatMoney(item.total, currency)}</span>
                  </button>
                )}
                {isExpanded && (
                  <div className="border-t border-border p-3">
                    {categoryMerchants.isLoading && <Skeleton className="h-16 w-full" />}
                    {categoryMerchants.data && categoryMerchants.data.items.length === 0 && (
                      <p className="text-sm text-text-muted">Nessun merchant per questa categoria.</p>
                    )}
                    {categoryMerchants.data && categoryMerchants.data.items.length > 0 && (
                      <ul className="flex flex-col gap-1">
                        {categoryMerchants.data.items.map((merchant) => (
                          <li key={merchant.merchant} className="flex items-center justify-between text-sm">
                            <span className="text-text-muted">{merchant.merchant}</span>
                            <span className="font-numeric text-text-muted">
                              {formatMoney(merchant.total, currency)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {byMerchant.isLoading && <Skeleton className="h-40 w-full" />}
      {byMerchant.data && byMerchant.data.items.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Merchant</h3>
          <ul className="flex flex-col gap-1">
            {byMerchant.data.items.slice(0, 10).map((item) => (
              <li key={item.merchant} className="flex items-center justify-between text-sm">
                <span className="text-text">{item.merchant}</span>
                <span className="font-numeric text-text-muted">{formatMoney(item.total, currency)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
