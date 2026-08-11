import { Landmark, PiggyBank, UploadCloud, Wallet } from "lucide-react";
import { Link } from "react-router-dom";

import { BarComparisonChart } from "../../components/charts/BarComparisonChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DonutChart } from "../../components/charts/DonutChart";
import { PeriodFilter } from "../../components/filters/PeriodFilter";
import { KpiCard } from "../../components/kpi/KpiCard";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { Skeleton, SkeletonRows } from "../../components/ui/Skeleton";
import { formatDate, formatMoney, formatPeriodLabel, formatSignedMoney } from "../../lib/format";
import { usePeriodFilter } from "../../lib/usePeriodFilter";
import { useTransactions } from "../transactions/api";
import { useAnalyticsByCategory, useAnalyticsCashFlow, useAnalyticsSummary } from "../analytics/api";
import { formatBucketLabel, greetingForHour } from "../analytics/chartData";

export function DashboardPage() {
  const { dateFrom, dateTo } = usePeriodFilter();
  const period = { date_from: dateFrom, date_to: dateTo };

  const summary = useAnalyticsSummary(period);
  const cashFlow = useAnalyticsCashFlow({ ...period, granularity: "month" });
  const byCategory = useAnalyticsByCategory({ ...period, direction: "expense" });
  const recentTransactions = useTransactions({ limit: 5 });

  const currency = summary.data?.currency ?? "EUR";
  const comparisonLabel = summary.data
    ? `vs ${formatPeriodLabel(summary.data.comparison_period.date_from, summary.data.comparison_period.date_to)}`
    : undefined;
  const cashFlowIsEmpty = cashFlow.data?.points.every((p) => p.income === "0" && p.expenses === "0") ?? false;
  const cashFlowPoints = cashFlow.data?.points ?? [];
  const cashFlowGranularity = cashFlow.data?.granularity ?? "month";

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">{greetingForHour(new Date().getHours())}</h1>
          <p className="text-sm text-text-muted">Panoramica finanziaria</p>
        </div>
        <PeriodFilter />
      </div>

      {summary.isError && (
        <ErrorState message="Non siamo riusciti a caricare la panoramica." onRetry={() => void summary.refetch()} />
      )}

      {summary.isLoading && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      )}

      {summary.data && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard title="Liquidità" value={summary.data.liquidity} currency={currency} />
          <KpiCard
            title="Entrate"
            value={summary.data.income}
            previousValue={summary.data.previous_income}
            comparisonLabel={comparisonLabel}
            currency={currency}
          />
          <KpiCard
            title="Spese"
            value={summary.data.expenses}
            previousValue={summary.data.previous_expenses}
            comparisonLabel={comparisonLabel}
            currency={currency}
            positiveIsGood={false}
          />
          <KpiCard
            title="Cash Flow"
            value={summary.data.net_cash_flow}
            previousValue={summary.data.previous_net_cash_flow}
            comparisonLabel={comparisonLabel}
            currency={currency}
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
              />
            </ChartCard>
          )}
        </div>

        {summary.data && (
          <Card className="flex h-full flex-col gap-2">
            <h3 className="text-sm font-semibold text-text">Investimenti</h3>
            {/* Il saldo dei conti titoli conta gia' come Liquidita' (sono
                spesso ibridi: spendibili con carta E usati per investire,
                es. Trade Republic/Fineco) — il valore reale delle posizioni
                arriva solo col modulo Portfolio, non da account_type. */}
            <EmptyState
              icon={PiggyBank}
              title="Il valore delle posizioni arriva con Portfolio"
              description="Il saldo dei tuoi conti, incluso quelli titoli, è già in Liquidità. Azioni, ETF e obbligazioni saranno tracciati con il modulo Portfolio."
            />
          </Card>
        )}
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
                  data={byCategory.data.items.map((item) => ({ label: item.name, value: Number(item.total) }))}
                />
              </ChartCard>
              {byCategory.data.items.length > 0 && (
                <ul className="flex flex-col gap-1.5">
                  {byCategory.data.items.map((item) => (
                    <li key={item.category_id ?? "none"} className="flex items-center justify-between text-sm">
                      <span className="text-text">{item.name}</span>
                      <span className="font-numeric text-text-muted">{formatMoney(item.total, currency)}</span>
                    </li>
                  ))}
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
    </div>
  );
}
