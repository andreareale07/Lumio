import { useState } from "react";
import type { ComponentType } from "react";
import { useTranslation } from "react-i18next";

import { ChartCard } from "../../components/charts/ChartCard";
import { DrillDownDrawer } from "../../components/charts/DrillDownDrawer";
import { LineComparisonChart } from "../../components/charts/LineComparisonChart";
import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { KpiCard } from "../../components/kpi/KpiCard";
import { usePageToolbar } from "../../components/layout/PageToolbarContext";
import { BackLink } from "../../components/ui/BackLink";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatMoney, formatPercent, formatPeriodLabel, intlLocale } from "../../lib/format";
import { GRANULARITY_ORDER, calculatePeriodComparison, previousPeriod, slidingWindow, type Granularity } from "../../lib/period";
import { mean, median, movingMedian } from "../../lib/stats";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import { useTransactions } from "../transactions/api";
import type { AnalyticsDirection } from "../../types/api";
import { useAnalyticsByCategory, useAnalyticsByMerchant, useAnalyticsCashFlow, useAnalyticsSummary } from "./api";
import { AnomalyInsights } from "./AnomalyInsights";
import { formatBucketLabel } from "./chartData";
import { CategoryHierarchyList } from "./CategoryHierarchyList";
import { RecurringInsights } from "./RecurringInsights";

const MERCHANT_DISPLAY_LIMIT = 10;

// Quanti bucket indietro corrisponde "un anno fa" per ciascuna granularita'
// offerta da questa pagina (month/quarter/year) — usato per il confronto
// anno-su-anno SENZA una richiesta separata: la finestra trend viene
// allargata (vedi YOY_WINDOW_SIZE) cosi' il bucket di un anno fa e' gia'
// dentro la serie scaricata per il grafico Andamento.
const YOY_OFFSET: Partial<Record<Granularity, number>> = { month: 12, quarter: 4, year: 1 };
const YOY_WINDOW_SIZE: Partial<Record<Granularity, number>> = { month: 13, quarter: 8, year: 5 };

interface BreakdownPageProps {
  direction: AnalyticsDirection;
  title: string;
  icon: ComponentType<{ className?: string }>;
  emptyDescription: string;
  hierarchyTitle: string;
  merchantsTitle: string;
  /** Spese: mostra la card "Ritmo" (€/giorno + proiezione fine periodo).
   * Entrate: mostra invece "Stabilita'" (mesi con entrate + concentrazione
   * sorgente) — un tasso giornaliero non ha senso per uno stipendio. */
  showDailyRate: boolean;
  showStability: boolean;
}

/** Base condivisa di `/expenses` e `/income` (redesign, FETTA 1 del piano
 * "entrate/spese ridisegnate"): risponde a quattro domande — dove vanno i
 * soldi (gerarchia categoria/sottocategoria/merchant/movimenti), come
 * cambiano nel tempo (andamento + mediana mobile + confronto anno su anno),
 * cosa si ripete/e' anomalo (slot separato), quanto e con che ritmo (striscia
 * KPI). Cambia solo `direction` e le etichette fra le due pagine. */
export function BreakdownPage({
  direction,
  title,
  icon,
  emptyDescription,
  hierarchyTitle,
  merchantsTitle,
  showDailyRate,
  showStability,
}: BreakdownPageProps) {
  const { t } = useTranslation(["analytics", "dashboard"]);
  const { granularity, currentPeriod, anchor } = usePeriodNavigator({
    granularities: GRANULARITY_ORDER,
  });
  const period = { date_from: currentPeriod.date_from, date_to: currentPeriod.date_to };
  const previousRange = previousPeriod(period.date_from, period.date_to);
  const [selectedCategory, setSelectedCategory] = useState<{ id: string; name: string } | null>(null);

  const summary = useAnalyticsSummary(period);
  const byCategory = useAnalyticsByCategory({ ...period, direction });
  const byMerchant = useAnalyticsByMerchant({ ...period, direction });

  // Finestra allargata per il grafico Andamento — contiene GIA' lo stesso
  // bucket di un anno fa (13 mesi / 8 trimestri / 5 anni), cosi' il
  // confronto anno-su-anno non richiede una seconda chiamata: si legge
  // semplicemente `series[length-1-offset]` (§ piano di sessione).
  const yoyWindow = slidingWindow(granularity, anchor, YOY_WINDOW_SIZE[granularity] ?? 6);
  const trendCashFlow = useAnalyticsCashFlow({ ...yoyWindow, granularity });

  // Media/mediana mensile (SPEC §30): scoperta al periodo corrente, non alla
  // finestra trend — per granularity="year" coincide con l'anno civile
  // selezionato (12 mesi), per "quarter" con i 3 mesi del trimestre, per
  // "month" con l'unico mese in vista (caso degenere ma non sbagliato).
  const monthlyBreakdown = useAnalyticsCashFlow({ ...period, granularity: "month" });

  // Dati del drawer di drill-down: fetch solo quando una categoria e'
  // selezionata, tutti scoperti da `selectedCategory.id`.
  const drawerCashFlow = useAnalyticsCashFlow(
    { ...yoyWindow, granularity, category_id: selectedCategory?.id },
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

  const bucketLabelStrings = {
    locale: intlLocale(),
    quarterAbbrev: t("common:period.quarterAbbrev"),
    semesterAbbrev: t("common:period.semesterAbbrev"),
  };

  const currency = summary.data?.currency ?? "EUR";

  // --- KPI "Totale" ---------------------------------------------------
  const totalValue = direction === "expense" ? summary.data?.expenses : summary.data?.income;
  const previousValue = direction === "expense" ? summary.data?.previous_expenses : summary.data?.previous_income;
  const comparisonSuffix =
    granularity === "year" ? t("breakdown.comparisonYearSuffix") : t("dashboard:drillDown.comparisonSuffix");

  // --- Andamento: valore + mediana mobile + confronto anno su anno ----
  const trendGranularity = trendCashFlow.data?.granularity ?? granularity;
  const trendPoints = trendCashFlow.data?.points ?? [];
  const trendValues = trendPoints.map((p) => Number(direction === "expense" ? p.expenses : p.income));
  // Un bucket senza NESSUN dato di workspace (entrate E spese entrambe zero)
  // e' quasi sempre precedente al primo movimento importato, non un bucket
  // di spesa/entrata zero reale — stessa euristica gia' introdotta in
  // Dashboard per "mesi di autonomia"/"vs mese tipico".
  const ghostMask = trendPoints.map((p) => Number(p.income) !== 0 || Number(p.expenses) !== 0);
  const trendValuesWithData = trendValues.filter((_, i) => ghostMask[i]);
  const trendAverage = trendValuesWithData.length > 0 ? mean(trendValuesWithData) : undefined;
  const trendMedianValue = trendValuesWithData.length > 0 ? median(trendValuesWithData) : undefined;
  const movingMedianSeries = movingMedian(trendValues, 3);

  const yoyOffset = YOY_OFFSET[granularity];
  const yoyCurrentIndex = trendValues.length - 1;
  const yoyPriorIndex = yoyOffset !== undefined ? yoyCurrentIndex - yoyOffset : -1;
  const yoyPriorValue =
    yoyPriorIndex >= 0 && ghostMask[yoyPriorIndex] ? trendValues[yoyPriorIndex] : undefined;
  const yoyComparison =
    yoyCurrentIndex >= 0
      ? calculatePeriodComparison(trendValues[yoyCurrentIndex]!, yoyPriorValue, direction === "income")
      : undefined;

  const trendChartData = trendPoints.map((p, i) => ({
    period: p.period,
    label: formatBucketLabel(p.period, trendGranularity, bucketLabelStrings),
    value: trendValues[i]!,
    typical: movingMedianSeries[i]!,
  }));

  // --- Rhythm: media/mediana mensile, ritmo giornaliero, movimenti ----
  const monthlyPoints = monthlyBreakdown.data?.points ?? [];
  const monthlyPointsWithData = monthlyPoints.filter((p) => Number(p.income) !== 0 || Number(p.expenses) !== 0);
  const monthlyValues = monthlyPointsWithData.map((p) => Number(direction === "expense" ? p.expenses : p.income));
  const monthlyAverage = monthlyValues.length > 0 ? mean(monthlyValues) : undefined;
  const monthlyMedianValue = monthlyValues.length > 0 ? median(monthlyValues) : undefined;

  const now = new Date();
  const periodFromDate = new Date(`${period.date_from}T00:00:00`);
  const periodToDate = new Date(`${period.date_to}T00:00:00`);
  const isCurrentPeriod = now >= periodFromDate && now <= periodToDate;
  const totalDaysInPeriod = Math.round((periodToDate.getTime() - periodFromDate.getTime()) / 86_400_000) + 1;
  const elapsedDays = isCurrentPeriod
    ? Math.round((now.getTime() - periodFromDate.getTime()) / 86_400_000) + 1
    : totalDaysInPeriod;
  const totalNumber = totalValue !== undefined ? Number(totalValue) : undefined;
  const dailyRate = totalNumber !== undefined && elapsedDays > 0 ? totalNumber / elapsedDays : undefined;
  const isPartialPeriod = isCurrentPeriod && elapsedDays < totalDaysInPeriod;
  const projection = isPartialPeriod && dailyRate !== undefined ? dailyRate * totalDaysInPeriod : undefined;

  const monthsWithIncome = monthlyPoints.filter((p) => Number(p.income) > 0).length;
  const topSource = byCategory.data?.items[0];

  const transactionsCount = (byCategory.data?.items ?? []).reduce((sum, item) => sum + item.transactions_count, 0);
  const averagePerTransaction =
    totalNumber !== undefined && transactionsCount > 0 ? totalNumber / transactionsCount : undefined;

  // --- Drill-down categoria (invariato, condiviso con la Dashboard) ---
  const drawerGranularity = drawerCashFlow.data?.granularity ?? granularity;
  const drawerTrendPoints = (drawerCashFlow.data?.points ?? []).map((p) => ({
    period: p.period,
    label: formatBucketLabel(p.period, drawerGranularity, bucketLabelStrings),
    value: Number(direction === "expense" ? p.expenses : p.income),
  }));
  const currentCategoryTotal = byCategory.data?.items.find((i) => i.category_id === selectedCategory?.id)?.total;
  const previousCategoryTotal = drawerPreviousCategory.data?.items.find(
    (i) => i.category_id === selectedCategory?.id,
  )?.total;
  const isDrawerLoading =
    drawerCashFlow.isLoading || drawerMerchants.isLoading || drawerPreviousCategory.isLoading || drawerTransactions.isLoading;

  // --- Top merchant / Top sorgenti -------------------------------------
  const merchantItems = byMerchant.data?.items ?? [];
  const visibleMerchants = merchantItems.slice(0, MERCHANT_DISPLAY_LIMIT);
  const otherMerchants = merchantItems.slice(MERCHANT_DISPLAY_LIMIT);
  const otherMerchantsTotal = otherMerchants.reduce((sum, m) => sum + Number(m.total), 0);
  const maxMerchantTotal = Math.max(1, ...merchantItems.map((m) => Number(m.total)));

  const periodNav = <PeriodNavigator granularities={GRANULARITY_ORDER} />;
  const toolbarPortal = usePageToolbar(periodNav);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      {toolbarPortal}
      <BackLink to="/" label={t("navigation:items.dashboard")} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-lg font-semibold text-text">{title}</h1>
        <div className="md:hidden">{periodNav}</div>
      </div>

      {summary.isError && <ErrorState message={t("breakdown.errorMessage")} onRetry={() => void summary.refetch()} />}

      {/* --- Striscia KPI: "quanto e con che ritmo" --- */}
      {summary.isLoading && (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      )}
      {summary.data && totalValue !== undefined && (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            title={t("breakdown.rhythm.total")}
            value={totalValue}
            previousValue={previousValue}
            comparisonLabel={comparisonSuffix}
            positiveIsGood={direction === "income"}
            currency={currency}
          />
          <div className="flex flex-col gap-1">
            <span className="text-sm text-text-muted">{t("breakdown.rhythm.average")}</span>
            <span className="font-numeric text-2xl font-semibold text-text">
              {monthlyAverage !== undefined ? formatMoney(monthlyAverage, currency) : t("breakdown.rhythm.notAvailable")}
            </span>
            {monthlyMedianValue !== undefined && (
              <span className="text-sm text-text-muted">
                {t("breakdown.rhythm.median", { value: formatMoney(monthlyMedianValue, currency) })}
              </span>
            )}
          </div>
          {showDailyRate && (
            <div className="flex flex-col gap-1">
              <span className="text-sm text-text-muted">{t("breakdown.rhythm.dailyRateTitle")}</span>
              <span className="font-numeric text-2xl font-semibold text-text">
                {dailyRate !== undefined
                  ? t("breakdown.rhythm.dailyRateValue", { value: formatMoney(dailyRate, currency) })
                  : t("breakdown.rhythm.notAvailable")}
              </span>
              {projection !== undefined && (
                <span className="text-sm text-text-muted">
                  {t("breakdown.rhythm.projection", { value: formatMoney(projection, currency) })}
                </span>
              )}
            </div>
          )}
          {showStability && (
            <div className="flex flex-col gap-1">
              <span className="text-sm text-text-muted">{t("breakdown.stability.title")}</span>
              <span className="font-numeric text-2xl font-semibold text-text">
                {t("breakdown.stability.monthsWithIncome", { count: monthsWithIncome, total: monthlyPoints.length })}
              </span>
              {topSource && Number(topSource.share) > 0 && (
                <span className="text-sm text-text-muted">
                  {t("breakdown.stability.concentration", {
                    share: `${Math.round(Number(topSource.share) * 100)}%`,
                    source: topSource.name,
                  })}
                </span>
              )}
            </div>
          )}
          <div className="flex flex-col gap-1">
            <span className="text-sm text-text-muted">{t("breakdown.rhythm.transactionsCount")}</span>
            <span className="font-numeric text-2xl font-semibold text-text">{transactionsCount}</span>
            {averagePerTransaction !== undefined && (
              <span className="text-sm text-text-muted">
                {t("breakdown.rhythm.averagePerTransaction", { value: formatMoney(averagePerTransaction, currency) })}
              </span>
            )}
          </div>
        </div>
      )}

      {/* --- Andamento: valore + mediana mobile + vs anno scorso --- */}
      {trendCashFlow.isLoading && <Skeleton className="h-64 w-full" />}
      {trendCashFlow.data && (
        <ChartCard
          title={t("breakdown.trend.title")}
          subtitle={formatPeriodLabel(yoyWindow.date_from, yoyWindow.date_to)}
          empty={trendValues.every((v) => v === 0)}
          emptyState={<EmptyState icon={icon} title={t("breakdown.trend.emptyTitle")} description={emptyDescription} />}
          tableCaption={t("breakdown.trend.tableCaption")}
          tableHeaders={t("breakdown.trend.tableHeaders", { returnObjects: true }) as string[]}
          tableRows={trendChartData.map((p) => [p.label, formatMoney(p.value, currency), formatMoney(p.typical, currency)])}
          footer={
            <p className="text-sm text-text-muted">
              {[
                trendAverage !== undefined ? t("breakdown.trend.averagePart", { value: formatMoney(trendAverage, currency) }) : null,
                trendMedianValue !== undefined
                  ? t("breakdown.trend.medianPart", { value: formatMoney(trendMedianValue, currency) })
                  : null,
                yoyComparison?.change !== undefined
                  ? t("breakdown.trend.yoyPart", { value: formatPercent(yoyComparison.change, { signed: true }) })
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          }
        >
          <LineComparisonChart
            currency={currency}
            data={trendChartData}
            series={[
              { key: "value", label: title, tone: direction === "expense" ? "danger" : "success" },
              { key: "typical", label: t("breakdown.trend.typicalLabel"), tone: "muted", dashed: true },
            ]}
          />
        </ChartCard>
      )}

      {/* --- Dove vanno i soldi / Da dove arrivano --- */}
      <CategoryHierarchyList
        direction={direction}
        currency={currency}
        icon={icon}
        title={hierarchyTitle}
        emptyDescription={emptyDescription}
        period={period}
        trendWindow={{ date_from: yoyWindow.date_from, date_to: yoyWindow.date_to }}
        granularity={trendGranularity}
        ghostMask={ghostMask}
        onSelectRow={(id, name) => setSelectedCategory({ id, name })}
      />

      {/* --- Cosa si ripete / cosa è anomalo (FETTA 2) --- */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RecurringInsights direction={direction} />
        <AnomalyInsights direction={direction} dateFrom={period.date_from} dateTo={period.date_to} />
      </div>

      {/* --- Top merchant / Top sorgenti --- */}
      {byMerchant.isLoading && <Skeleton className="h-64 w-full" />}
      {byMerchant.data && (
        <ChartCard
          title={merchantsTitle}
          chartClassName="h-auto"
          empty={merchantItems.length === 0}
          emptyState={<EmptyState icon={icon} title={t("breakdown.merchants.emptyTitle")} description={emptyDescription} />}
          tableCaption={t("breakdown.merchants.tableCaption")}
          tableHeaders={t("breakdown.merchants.tableHeaders", { returnObjects: true }) as string[]}
          tableRows={merchantItems.map((m) => [
            m.merchant,
            formatMoney(m.total, currency),
            `${Math.round(Number(m.share) * 100)}%`,
            m.transactions_count,
          ])}
        >
          <ul className="flex flex-col gap-3">
            {visibleMerchants.map((m) => {
              const barPct = Math.round((Number(m.total) / maxMerchantTotal) * 100);
              return (
                <li key={m.merchant} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="truncate text-text">{m.merchant}</span>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="text-xs text-text-muted">{Math.round(Number(m.share) * 100)}%</span>
                      <span className="font-numeric text-text">{formatMoney(m.total, currency)}</span>
                    </div>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-hover">
                    <div className="h-full rounded-full bg-primary" style={{ width: `${barPct}%` }} />
                  </div>
                </li>
              );
            })}
            {otherMerchants.length > 0 && (
              <li className="flex items-center justify-between pt-1 text-sm text-text-muted">
                <span>{t("breakdown.merchants.othersRow", { count: otherMerchants.length })}</span>
                <span className="font-numeric">{formatMoney(otherMerchantsTotal, currency)}</span>
              </li>
            )}
          </ul>
        </ChartCard>
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
