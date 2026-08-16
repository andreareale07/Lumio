import { useState } from "react";
import { Landmark, PiggyBank, UploadCloud, Wallet } from "lucide-react";
import { Link } from "react-router-dom";

import { BarComparisonChart, type CashFlowBarPoint } from "../../components/charts/BarComparisonChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DonutChart } from "../../components/charts/DonutChart";
import { DrillDownDrawer } from "../../components/charts/DrillDownDrawer";
import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { KpiCard } from "../../components/kpi/KpiCard";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { Skeleton, SkeletonRows } from "../../components/ui/Skeleton";
import { formatDate, formatMoney, formatPercent, formatPeriodLabel, formatSignedMoney } from "../../lib/format";
import { periodForAnchor, previousPeriod, type Granularity } from "../../lib/period";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import { useTransactions } from "../transactions/api";
import {
  useAnalyticsBalanceHistory,
  useAnalyticsByCategory,
  useAnalyticsByMerchant,
  useAnalyticsCashFlow,
  useAnalyticsSummary,
} from "../analytics/api";
import { formatBucketLabel, greetingForHour } from "../analytics/chartData";
import { usePortfolioAllocation, usePortfolioValuation } from "../portfolio/api";

export function DashboardPage() {
  const { granularity, currentPeriod, trendWindow } = usePeriodNavigator({
    granularities: ["month", "quarter", "year"],
  });
  const period = { date_from: currentPeriod.date_from, date_to: currentPeriod.date_to };
  const previousRange = previousPeriod(period.date_from, period.date_to);

  const summary = useAnalyticsSummary(period);
  const cashFlow = useAnalyticsCashFlow({ ...trendWindow, granularity });
  const balanceHistory = useAnalyticsBalanceHistory({ ...trendWindow, granularity });
  const byCategory = useAnalyticsByCategory({ ...period, direction: "expense" });
  const recentTransactions = useTransactions({ limit: 5 });

  const currency = summary.data?.currency ?? "EUR";
  const comparisonLabel = summary.data
    ? `vs ${formatPeriodLabel(summary.data.comparison_period.date_from, summary.data.comparison_period.date_to)}`
    : undefined;
  const cashFlowIsEmpty = cashFlow.data?.points.every((p) => p.income === "0" && p.expenses === "0") ?? false;
  const cashFlowPoints = cashFlow.data?.points ?? [];
  const cashFlowGranularity = (cashFlow.data?.granularity ?? "month") as Granularity;

  const liquiditySparkline = (balanceHistory.data?.points ?? []).map((p) => Number(p.balance));
  const incomeSparkline = cashFlowPoints.map((p) => Number(p.income));
  const expensesSparkline = cashFlowPoints.map((p) => Number(p.expenses));
  const cashFlowSparkline = cashFlowPoints.map((p) => Number(p.income) - Number(p.expenses));

  // Drill-down categoria (Step A, riusato qui): stessa forma di
  // BreakdownPage.tsx, sempre direction="expense" (l'unico donut qui).
  const [selectedCategory, setSelectedCategory] = useState<{ id: string; name: string } | null>(null);
  const drawerCashFlow = useAnalyticsCashFlow(
    { ...trendWindow, granularity, category_id: selectedCategory?.id },
    { enabled: !!selectedCategory },
  );
  const drawerMerchants = useAnalyticsByMerchant(
    { ...period, direction: "expense", category_id: selectedCategory?.id },
    { enabled: !!selectedCategory },
  );
  const drawerPreviousCategory = useAnalyticsByCategory(
    { ...previousRange, direction: "expense" },
    { enabled: !!selectedCategory },
  );
  const drawerCategoryTransactions = useTransactions(
    { category_id: selectedCategory?.id, date_from: period.date_from, date_to: period.date_to, limit: 5 },
    { enabled: !!selectedCategory },
  );
  const categoryDrawerGranularity = (drawerCashFlow.data?.granularity ?? "month") as Granularity;
  const categoryDrawerTrend = (drawerCashFlow.data?.points ?? []).map((p) => ({
    period: p.period,
    label: formatBucketLabel(p.period, categoryDrawerGranularity),
    value: Number(p.expenses),
  }));
  const currentCategoryTotal = byCategory.data?.items.find((i) => i.category_id === selectedCategory?.id)?.total;
  const previousCategoryTotal = drawerPreviousCategory.data?.items.find(
    (i) => i.category_id === selectedCategory?.id,
  )?.total;

  // Drill-down periodo (click su una barra Entrate/Uscite): un bucket
  // temporale non ha "categorie", solo il confronto entrate/uscite di
  // QUEL periodo + le transazioni che ci sono cadute dentro.
  const [selectedBucket, setSelectedBucket] = useState<CashFlowBarPoint | null>(null);
  const bucketRange = selectedBucket ? periodForAnchor(cashFlowGranularity, new Date(selectedBucket.period)) : null;
  const bucketTransactions = useTransactions(
    { date_from: bucketRange?.date_from, date_to: bucketRange?.date_to, limit: 5 },
    { enabled: !!selectedBucket },
  );

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">{greetingForHour(new Date().getHours())}</h1>
          <p className="text-sm text-text-muted">Panoramica finanziaria</p>
        </div>
        <PeriodNavigator granularities={["month", "quarter", "year"]} />
      </div>

      {summary.isError && (
        <ErrorState message="Non siamo riusciti a caricare la panoramica." onRetry={() => void summary.refetch()} />
      )}

      {summary.isLoading && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      )}

      {summary.data && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard title="Patrimonio totale" value={summary.data.net_worth} currency={currency} />
          <KpiCard
            title="Liquidità"
            value={summary.data.liquidity}
            currency={currency}
            sparklineValues={liquiditySparkline.length > 1 ? liquiditySparkline : undefined}
          />
          <KpiCard title="Investimenti" value={summary.data.investments} currency={currency} />
          <KpiCard title="Debiti" value={summary.data.debt} currency={currency} positiveIsGood={false} />
          <KpiCard
            title="Entrate"
            value={summary.data.income}
            previousValue={summary.data.previous_income}
            comparisonLabel={comparisonLabel}
            currency={currency}
            sparklineValues={incomeSparkline.length > 1 ? incomeSparkline : undefined}
          />
          <KpiCard
            title="Spese"
            value={summary.data.expenses}
            previousValue={summary.data.previous_expenses}
            comparisonLabel={comparisonLabel}
            currency={currency}
            positiveIsGood={false}
            sparklineValues={expensesSparkline.length > 1 ? expensesSparkline : undefined}
          />
          <KpiCard
            title="Cash Flow"
            value={summary.data.net_cash_flow}
            previousValue={summary.data.previous_net_cash_flow}
            comparisonLabel={comparisonLabel}
            currency={currency}
            sparklineValues={cashFlowSparkline.length > 1 ? cashFlowSparkline : undefined}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {cashFlow.isLoading && <Skeleton className="h-72 w-full" />}
          {cashFlow.isError && (
            <ErrorState message="Grafico non disponibile." onRetry={() => void cashFlow.refetch()} />
          )}
          {cashFlow.data && (
            <ChartCard
              title="Entrate vs Uscite"
              subtitle={formatPeriodLabel(cashFlow.data.period.date_from, cashFlow.data.period.date_to)}
              empty={cashFlowIsEmpty}
              emptyState={
                <EmptyState
                  icon={Wallet}
                  title="Nessun movimento in questo periodo"
                  description="Importa un estratto conto per vedere entrate e uscite."
                  action={<LinkButton to="/imports" size="sm">Importa estratto conto</LinkButton>}
                />
              }
              tableCaption="Entrate e uscite per mese"
              tableHeaders={["Periodo", "Entrate", "Uscite"]}
              tableRows={cashFlowPoints.map((p) => [
                formatBucketLabel(p.period, cashFlowGranularity),
                formatMoney(p.income, currency),
                formatMoney(p.expenses, currency),
              ])}
            >
              <BarComparisonChart
                currency={currency}
                data={cashFlowPoints.map((p) => ({
                  period: p.period,
                  label: formatBucketLabel(p.period, cashFlowGranularity),
                  income: Number(p.income),
                  expenses: Number(p.expenses),
                }))}
                onBarClick={setSelectedBucket}
              />
            </ChartCard>
          )}
        </div>

        {/* Il saldo dei conti titoli conta gia' come Liquidita' (sono spesso
            ibridi: spendibili con carta E usati per investire, es. Trade
            Republic/Fineco) — questo widget mostra il valore delle
            POSIZIONI (asset posseduti), un dato distinto dal cash, mai
            doppio conteggio (M09b). */}
        <PortfolioWidget />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 flex flex-col gap-3">
          {byCategory.isLoading && <Skeleton className="h-72 w-full" />}
          {byCategory.isError && (
            <ErrorState message="Grafico non disponibile." onRetry={() => void byCategory.refetch()} />
          )}
          {byCategory.data && (
            <>
              <ChartCard
                title="Spese per categoria"
                subtitle={formatPeriodLabel(byCategory.data.period.date_from, byCategory.data.period.date_to)}
                empty={byCategory.data.items.length === 0}
                emptyState={
                  <EmptyState
                    icon={Landmark}
                    title="Nessuna spesa in questo periodo"
                    description="Le spese classificate appariranno qui, raggruppate per categoria."
                  />
                }
                tableCaption="Spese per categoria"
                tableHeaders={["Categoria", "Totale", "Quota"]}
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
              {byCategory.data.items.length > 0 && (
                <ul className="flex flex-col gap-1.5">
                  {byCategory.data.items.map((item) =>
                    item.category_id === null ? (
                      <li key="none" className="flex items-center justify-between text-sm">
                        <span className="text-text">{item.name}</span>
                        <span className="font-numeric text-text-muted">{formatMoney(item.total, currency)}</span>
                      </li>
                    ) : (
                      <li key={item.category_id}>
                        <button
                          type="button"
                          onClick={() => setSelectedCategory({ id: item.category_id as string, name: item.name })}
                          className="flex w-full items-center justify-between rounded-md p-1 text-left text-sm hover:bg-surface-hover"
                        >
                          <span className="text-text">{item.name}</span>
                          <span className="font-numeric text-text-muted">{formatMoney(item.total, currency)}</span>
                        </button>
                      </li>
                    ),
                  )}
                </ul>
              )}
            </>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-text">Ultimi movimenti</h3>
          {recentTransactions.isLoading && <SkeletonRows rows={4} />}
          {recentTransactions.isError && (
            <ErrorState message="Movimenti non disponibili." onRetry={() => void recentTransactions.refetch()} />
          )}
          {recentTransactions.data && recentTransactions.data.length === 0 && (
            <EmptyState
              icon={Wallet}
              title="Nessun movimento"
              description="I movimenti importati o creati manualmente appariranno qui."
            />
          )}
          {recentTransactions.data && recentTransactions.data.length > 0 && (
            <div className="flex flex-col gap-2">
              {recentTransactions.data.map((transaction) => (
                <Link
                  key={transaction.id}
                  to="/transactions"
                  className="flex items-center justify-between rounded-lg border border-border bg-surface p-3 text-sm hover:bg-surface-hover"
                >
                  <div className="flex flex-col">
                    <span className="text-text">{transaction.merchant ?? transaction.description_raw}</span>
                    <span className="text-text-muted">{formatDate(transaction.transaction_date)}</span>
                  </div>
                  <span className="font-numeric text-text">
                    {formatSignedMoney(transaction.amount, transaction.currency)}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <LinkButton to="/imports">
          <UploadCloud className="h-4 w-4" aria-hidden="true" /> Importa estratto conto
        </LinkButton>
        <LinkButton to="/accounts" variant="secondary">
          <Landmark className="h-4 w-4" aria-hidden="true" /> Aggiungi conto
        </LinkButton>
        <LinkButton to="/transactions" variant="secondary">
          <Wallet className="h-4 w-4" aria-hidden="true" /> Visualizza movimenti
        </LinkButton>
      </div>

      <DrillDownDrawer
        open={!!selectedCategory}
        onClose={() => setSelectedCategory(null)}
        title={selectedCategory?.name ?? ""}
        currency={currency}
        isLoading={
          drawerCashFlow.isLoading ||
          drawerMerchants.isLoading ||
          drawerPreviousCategory.isLoading ||
          drawerCategoryTransactions.isLoading
        }
        comparison={
          currentCategoryTotal !== undefined
            ? { current: Number(currentCategoryTotal), previous: Number(previousCategoryTotal ?? 0), higherIsGood: false }
            : undefined
        }
        trend={categoryDrawerTrend}
        breakdownTitle="Top merchant"
        breakdown={(drawerMerchants.data?.items ?? []).map((m) => ({
          key: m.merchant ?? "senza-merchant",
          label: m.merchant ?? "Senza merchant",
          value: Number(m.total),
        }))}
        transactions={(drawerCategoryTransactions.data ?? []).map((t) => ({
          id: t.id,
          label: t.merchant ?? t.description_raw,
          date: t.transaction_date,
          amount: t.amount,
          currency: t.currency,
        }))}
        viewAllHref={selectedCategory ? `/transactions?category=${selectedCategory.id}` : undefined}
      />

      <DrillDownDrawer
        open={!!selectedBucket}
        onClose={() => setSelectedBucket(null)}
        title={selectedBucket?.label ?? ""}
        currency={currency}
        isLoading={bucketTransactions.isLoading}
        breakdownTitle="Entrate vs Uscite"
        breakdown={
          selectedBucket
            ? [
                { key: "income", label: "Entrate", value: selectedBucket.income },
                { key: "expenses", label: "Uscite", value: selectedBucket.expenses },
              ]
            : undefined
        }
        transactions={(bucketTransactions.data ?? []).map((t) => ({
          id: t.id,
          label: t.merchant ?? t.description_raw,
          date: t.transaction_date,
          amount: t.amount,
          currency: t.currency,
        }))}
        viewAllHref={
          bucketRange ? `/transactions?mode=custom&from=${bucketRange.date_from}&to=${bucketRange.date_to}` : undefined
        }
      />
    </div>
  );
}

/** SPEC_FE §17 "Portfolio Widget": valore + performance + composizione, o
 * un empty state — mai un grafico vuoto se l'utente non ha investimenti
 * (SPEC §73). Aggregato su "tutti i conti" (nessun filtro portfolio qui,
 * la dashboard e' una vista d'insieme). */
function PortfolioWidget() {
  const valuation = usePortfolioValuation(null);
  const allocation = usePortfolioAllocation(null);

  if (valuation.isLoading) {
    return (
      <Card className="flex h-full flex-col gap-2">
        <Skeleton className="h-24 w-full" />
      </Card>
    );
  }
  if (valuation.isError) {
    return (
      <Card className="flex h-full flex-col gap-2">
        <h3 className="text-sm font-semibold text-text">Investimenti</h3>
        <ErrorState message="Portfolio non disponibile." onRetry={() => void valuation.refetch()} />
      </Card>
    );
  }

  const data = valuation.data;
  if (!data || !data.has_holdings) {
    return (
      <Card className="flex h-full flex-col gap-2">
        <h3 className="text-sm font-semibold text-text">Investimenti</h3>
        <EmptyState
          icon={PiggyBank}
          title="Non hai ancora aggiunto investimenti"
          description="Registra i tuoi acquisti in Investimenti per vederne qui il valore e la composizione."
          action={<LinkButton to="/investments" size="sm">Vai a Investimenti</LinkButton>}
        />
      </Card>
    );
  }

  const costBasis = Number(data.cost_basis);
  const performancePct = costBasis !== 0 ? Number(data.unrealized_pl) / costBasis : 0;
  const topAllocation = allocation.data?.by_asset_type.slice(0, 4) ?? [];

  return (
    <Card className="flex h-full flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-text">Investimenti</h3>
        <div className="flex items-baseline gap-2">
          <span className="font-numeric text-xl font-semibold text-text">
            {formatMoney(data.market_value, data.currency)}
          </span>
          {data.has_market_data && (
            <span className={`text-sm font-medium ${performancePct >= 0 ? "text-success" : "text-danger"}`}>
              {formatPercent(performancePct, { signed: true })}
            </span>
          )}
        </div>
      </div>
      {topAllocation.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {topAllocation.map((item) => (
            <li key={item.key} className="flex items-center justify-between text-text-muted">
              <span>{item.label}</span>
              <span className="font-numeric text-text">{formatPercent(item.share)}</span>
            </li>
          ))}
        </ul>
      )}
      <Link to="/investments" className="text-sm font-medium text-primary hover:underline">
        Vai a Investimenti
      </Link>
    </Card>
  );
}
