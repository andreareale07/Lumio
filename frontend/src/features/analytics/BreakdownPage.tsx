import { useState } from "react";
import type { ComponentType } from "react";
import { useTranslation } from "react-i18next";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DonutChart } from "../../components/charts/DonutChart";
import { DrillDownDrawer } from "../../components/charts/DrillDownDrawer";
import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatMoney, formatPercent, formatPeriodLabel } from "../../lib/format";
import { previousPeriod } from "../../lib/period";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import { useTransactions } from "../transactions/api";
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
  const { t } = useTranslation(["analytics", "dashboard"]);
  const { granularity: navGranularity, currentPeriod, trendWindow } = usePeriodNavigator({
    granularities: ["month", "quarter", "year"],
  });
  const period = { date_from: currentPeriod.date_from, date_to: currentPeriod.date_to };
  const previousRange = previousPeriod(period.date_from, period.date_to);
  const [selectedCategory, setSelectedCategory] = useState<{ id: string; name: string } | null>(null);

  const summary = useAnalyticsSummary(period);
  const cashFlow = useAnalyticsCashFlow({ ...trendWindow, granularity: navGranularity });
  const byCategory = useAnalyticsByCategory({ ...period, direction });
  const byMerchant = useAnalyticsByMerchant({ ...period, direction });

  // Dati del drawer di drill-down (SPEC_FE §30): fetch solo quando una
  // categoria e' selezionata, tutti scoperti da `selectedCategory.id`.
  const drawerCashFlow = useAnalyticsCashFlow(
    { ...trendWindow, granularity: navGranularity, category_id: selectedCategory?.id },
    { enabled: !!selectedCategory },
  );
  const drawerMerchants = useAnalyticsByMerchant(
    { ...period, direction, category_id: selectedCategory?.id },
    { enabled: !!selectedCategory },
  );
  const drawerPreviousCategory = useAnalyticsByCategory(
    { ...previousRange, direction },
    { enabled: !!selectedCategory },
  );
  const drawerTransactions = useTransactions(
    { category_id: selectedCategory?.id, date_from: period.date_from, date_to: period.date_to, limit: 5 },
    { enabled: !!selectedCategory },
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

  // Contenuto del drawer di drill-down per la categoria selezionata — un
  // solo posto che assembla i dati da 4 hook diversi nella forma richiesta
  // dal DrillDownDrawer generico (rework dashboard interattivo).
  const drawerGranularity = drawerCashFlow.data?.granularity ?? "month";
  const drawerTrendPoints = (drawerCashFlow.data?.points ?? []).map((p) => ({
    period: p.period,
    label: formatBucketLabel(p.period, drawerGranularity),
    value: Number(direction === "expense" ? p.expenses : p.income),
  }));
  const currentCategoryTotal = byCategory.data?.items.find((i) => i.category_id === selectedCategory?.id)?.total;
  const previousCategoryTotal = drawerPreviousCategory.data?.items.find(
    (i) => i.category_id === selectedCategory?.id,
  )?.total;
  const isDrawerLoading =
    drawerCashFlow.isLoading || drawerMerchants.isLoading || drawerPreviousCategory.isLoading || drawerTransactions.isLoading;

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
                  {formatPercent(change, { signed: true })} {t("dashboard:drillDown.comparisonSuffix")}
                </span>
              )}
            </div>
          )}
        </div>
        <PeriodNavigator granularities={["month", "quarter", "year"]} />
      </div>

      {summary.isError && <ErrorState message={t("breakdown.errorMessage")} onRetry={() => void summary.refetch()} />}

      {cashFlow.isLoading && <Skeleton className="h-64 w-full" />}
      {cashFlow.data && (
        <ChartCard
          title={t("breakdown.trendChart.title")}
          subtitle={formatPeriodLabel(cashFlow.data.period.date_from, cashFlow.data.period.date_to)}
          empty={trendPoints.every((p) => p.value === 0)}
          emptyState={<EmptyState icon={icon} title={t("breakdown.trendChart.emptyTitle")} description={emptyDescription} />}
          tableCaption={t("breakdown.trendChart.tableCaption")}
          tableHeaders={t("breakdown.trendChart.tableHeaders", { returnObjects: true }) as string[]}
          tableRows={trendPoints.map((p) => [p.label, formatMoney(p.value, currency)])}
        >
          <AreaTrendChart data={trendPoints} currency={currency} />
        </ChartCard>
      )}

      {byCategory.isLoading && <Skeleton className="h-64 w-full" />}
      {byCategory.data && (
        <ChartCard
          title={t("breakdown.categoryChart.title")}
          empty={byCategory.data.items.length === 0}
          emptyState={<EmptyState icon={icon} title={t("breakdown.categoryChart.emptyTitle")} description={emptyDescription} />}
          tableCaption={t("breakdown.categoryChart.tableCaption")}
          tableHeaders={t("breakdown.categoryChart.tableHeaders", { returnObjects: true }) as string[]}
          tableRows={byCategory.data.items.map((item) => [
            item.name,
            formatMoney(item.total, currency),
            `${Math.round(Number(item.share) * 100)}%`,
          ])}
        >
          <DonutChart
            currency={currency}
            data={byCategory.data.items.map((item) => ({
              key: item.category_id ?? undefined,
              label: item.name,
              value: Number(item.total),
            }))}
            onSliceClick={(slice) => slice.key && setSelectedCategory({ id: slice.key, name: slice.label })}
          />
        </ChartCard>
      )}

      {byCategory.data && byCategory.data.items.length > 0 && (
        <ul className="flex flex-col gap-1">
          {byCategory.data.items.map((item) => {
            const categoryId = item.category_id;
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
                    onClick={() => setSelectedCategory({ id: categoryId, name: item.name })}
                    className="flex w-full items-center justify-between p-3 text-left text-sm hover:bg-surface-hover"
                  >
                    <span className="text-text">{item.name}</span>
                    <span className="font-numeric text-text-muted">{formatMoney(item.total, currency)}</span>
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {byMerchant.isLoading && <Skeleton className="h-40 w-full" />}
      {byMerchant.data && byMerchant.data.items.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">{t("breakdown.merchants.title")}</h3>
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

      <DrillDownDrawer
        open={!!selectedCategory}
        onClose={() => setSelectedCategory(null)}
        title={selectedCategory?.name ?? ""}
        currency={currency}
        isLoading={isDrawerLoading}
        comparison={
          currentCategoryTotal !== undefined
            ? {
                current: Number(currentCategoryTotal),
                previous: Number(previousCategoryTotal ?? 0),
                higherIsGood: direction === "income",
              }
            : undefined
        }
        trend={drawerTrendPoints}
        breakdownTitle={t("breakdown.merchants.breakdownTitle")}
        breakdown={(drawerMerchants.data?.items ?? []).map((m) => ({
          key: m.merchant ?? "senza-merchant",
          label: m.merchant ?? t("breakdown.merchants.noMerchant"),
          value: Number(m.total),
        }))}
        transactions={(drawerTransactions.data ?? []).map((txn) => ({
          id: txn.id,
          label: txn.merchant ?? txn.description_raw,
          date: txn.transaction_date,
          amount: txn.amount,
          currency: txn.currency,
        }))}
        viewAllHref={selectedCategory ? `/transactions?category=${selectedCategory.id}` : undefined}
      />
    </div>
  );
}
