import { Landmark, PiggyBank } from "lucide-react";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { PeriodFilter } from "../../components/filters/PeriodFilter";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatMoney, formatPeriodLabel } from "../../lib/format";
import { usePeriodFilter } from "../../lib/usePeriodFilter";
import { useAnalyticsBalanceHistory, useAnalyticsBalances, useAnalyticsSummary } from "./api";
import { formatBucketLabel } from "./chartData";

/** SPEC_FE §33-34: storico + breakdown per gruppo di conti + attribution
 * del periodo. Il dominio investimenti (assets/positions/performance) non
 * esiste ancora (arriva con M09): il saldo di QUALSIASI conto — incluso un
 * conto titoli, spesso ibrido (spendibile con carta E usato per investire,
 * es. Trade Republic/Fineco) — conta come Liquidita', non come
 * investimento. L'attribution si limita a Entrate/Spese/Totale — senza una
 * riga "Investimenti" separata, che richiederebbe dati di portfolio non
 * ancora disponibili. */
export function NetWorthPage() {
  const { dateFrom, dateTo } = usePeriodFilter();
  const period = { date_from: dateFrom, date_to: dateTo };

  const summary = useAnalyticsSummary(period);
  const balances = useAnalyticsBalances();
  const history = useAnalyticsBalanceHistory({ ...period, granularity: "month" });

  const currency = summary.data?.currency ?? "EUR";
  const granularity = history.data?.granularity ?? "month";
  const trendPoints = (history.data?.points ?? []).map((p) => ({
    period: p.period,
    label: formatBucketLabel(p.period, granularity),
    value: Number(p.balance),
  }));

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Patrimonio</h1>
          {summary.data && (
            <span className="font-numeric text-2xl font-semibold text-text">
              {formatMoney(summary.data.liquidity, currency)}
            </span>
          )}
          <p className="text-sm text-text-muted">
            Liquidità disponibile. Il valore delle posizioni di investimento arriva con il modulo Portfolio.
          </p>
        </div>
        <PeriodFilter />
      </div>

      {summary.isError && <ErrorState message="Dati non disponibili." onRetry={() => void summary.refetch()} />}

      {history.isLoading && <Skeleton className="h-72 w-full" />}
      {history.data && (
        <ChartCard
          title="Patrimonio nel tempo"
          subtitle={formatPeriodLabel(history.data.period.date_from, history.data.period.date_to)}
          empty={trendPoints.length === 0}
          emptyState={
            <EmptyState
              icon={Landmark}
              title="Nessun dato"
              description="Lo storico apparirà non appena avrai movimenti registrati."
            />
          }
          tableCaption="Patrimonio (liquidità) nel tempo"
          tableHeaders={["Periodo", "Saldo"]}
          tableRows={trendPoints.map((p) => [p.label, formatMoney(p.value, currency)])}
        >
          <AreaTrendChart data={trendPoints} currency={currency} />
        </ChartCard>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Composizione</h3>
          {balances.isLoading && <Skeleton className="h-24 w-full" />}
          {balances.data && (
            <ul className="flex flex-col gap-2 text-sm">
              <li className="flex items-center justify-between">
                <span className="text-text">Liquidità</span>
                <span className="font-numeric text-text">{formatMoney(balances.data.liquidity_total, currency)}</span>
              </li>
              {Number(balances.data.debt_total) !== 0 && (
                <li className="flex items-center justify-between">
                  <span className="text-text">Debiti</span>
                  <span className="font-numeric text-danger">{formatMoney(balances.data.debt_total, currency)}</span>
                </li>
              )}
            </ul>
          )}
          {/* Il saldo dei conti titoli conta gia' come Liquidita' sopra
              (sono spesso ibridi: spendibili con carta E usati per
              investire) — il valore reale delle posizioni arriva solo col
              modulo Portfolio. */}
          {balances.data && (
            <EmptyState
              icon={PiggyBank}
              title="Il valore delle posizioni arriva con Portfolio"
              description="Azioni, ETF e obbligazioni saranno tracciati con il modulo Portfolio, a prescindere dal tipo di conto."
            />
          )}
        </Card>

        <Card className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Variazione del periodo</h3>
          {summary.data && (
            <ul className="flex flex-col gap-2 text-sm">
              <li className="flex items-center justify-between">
                <span className="text-text">Entrate</span>
                <span className="font-numeric text-success">+{formatMoney(summary.data.income, currency)}</span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-text">Spese</span>
                <span className="font-numeric text-danger">-{formatMoney(summary.data.expenses, currency)}</span>
              </li>
              <li className="flex items-center justify-between border-t border-border pt-2 font-semibold">
                <span className="text-text">Totale</span>
                <span className="font-numeric text-text">
                  {Number(summary.data.net_cash_flow) >= 0 ? "+" : ""}
                  {formatMoney(summary.data.net_cash_flow, currency)}
                </span>
              </li>
            </ul>
          )}
          <p className="text-sm text-text-muted">
            Il movimento degli investimenti sarà scomposto separatamente con il modulo Portfolio (M09).
          </p>
        </Card>
      </div>
    </div>
  );
}
