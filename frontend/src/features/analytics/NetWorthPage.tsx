import { useState } from "react";
import { Landmark, PiggyBank, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DrillDownDrawer } from "../../components/charts/DrillDownDrawer";
import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { JobRunStatus } from "../../components/ui/JobRunStatus";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatDate, formatMoney } from "../../lib/format";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import { useTransactions } from "../transactions/api";
import { useSnapshotRebuildStatus, useTriggerSnapshotRebuild } from "../portfolio/api";
import { useAnalyticsBalances, useAnalyticsNetWorthHistory, useAnalyticsSummary } from "./api";

const LIQUIDITY_ACCOUNT_TYPES = new Set(["checking", "savings", "brokerage", "cash", "other"]);
const DEBT_ACCOUNT_TYPES = new Set(["credit_card"]);

/** SPEC_FE §33-34: storico + breakdown per gruppo di conti + attribution
 * del periodo. Il saldo di QUALSIASI conto — incluso un conto titoli,
 * spesso ibrido (spendibile con carta E usato per investire, es. Trade
 * Republic/Fineco) — conta come Liquidita', non come investimento: un
 * acquisto reale sposta cash verso una posizione, valorizzata separatamente
 * (M09b, `balances.investment_total`) — mai un doppio conteggio.
 *
 * Rework dashboard interattivo: il grafico storico usa ora
 * `net-worth-history` (vero patrimonio, liquidita'+debiti+investimenti a
 * valore di mercato, letto SEMPRE dagli snapshot gia' scritti) invece di
 * `balance-history` (sola liquidita', ricostruita a ritroso dalle
 * transazioni) — endpoint gia' esistente, mai collegato prima. Nessun
 * "recompute vs snapshot" da riconciliare: a differenza della vecchia
 * versione (che avrebbe dovuto mischiare una serie ricalcolata con una da
 * snapshot), qui l'intera serie viene da UNA sola fonte, gli snapshot. */
export function NetWorthPage() {
  const { currentPeriod, trendWindow } = usePeriodNavigator({
    granularities: ["month", "quarter", "year"],
  });

  const summary = useAnalyticsSummary({ date_from: currentPeriod.date_from, date_to: currentPeriod.date_to });
  const balances = useAnalyticsBalances();
  const history = useAnalyticsNetWorthHistory({ date_from: trendWindow.date_from, date_to: trendWindow.date_to });
  const rebuildSnapshot = useTriggerSnapshotRebuild();
  const rebuildStatus = useSnapshotRebuildStatus();

  const [selectedComposition, setSelectedComposition] = useState<"liquidity" | "debt" | null>(null);
  const compositionTransactions = useTransactions({ limit: 5 }, { enabled: !!selectedComposition });

  const currency = summary.data?.currency ?? "EUR";
  const trendPoints = (history.data?.points ?? []).map((p) => ({
    period: p.snapshot_date,
    label: formatDate(p.snapshot_date),
    value: Number(p.net_worth),
  }));

  const compositionAccounts = (balances.data?.accounts ?? []).filter((a) =>
    selectedComposition === "liquidity"
      ? LIQUIDITY_ACCOUNT_TYPES.has(a.account_type)
      : selectedComposition === "debt"
        ? DEBT_ACCOUNT_TYPES.has(a.account_type)
        : false,
  );

  const onRebuildNow = async () => {
    await rebuildSnapshot.mutateAsync();
    // Stesso principio di InvestmentsPage.tsx > PerformanceTab: nessun
    // canale di progresso live, si ri-legge lo stato persistente dopo che
    // il worker ha avuto il tempo di scriverlo.
    setTimeout(() => {
      void history.refetch();
      void rebuildStatus.refetch();
    }, 1500);
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Patrimonio</h1>
          {summary.data && (
            <span className="font-numeric text-2xl font-semibold text-text">
              {formatMoney(summary.data.net_worth, currency)}
            </span>
          )}
          <p className="text-sm text-text-muted">Patrimonio totale: liquidità, debiti e investimenti.</p>
        </div>
        <PeriodNavigator granularities={["month", "quarter", "year"]} />
      </div>

      {summary.isError && <ErrorState message="Dati non disponibili." onRetry={() => void summary.refetch()} />}

      <div className="flex items-center justify-end gap-2">
        <Button variant="secondary" size="sm" loading={rebuildSnapshot.isPending} onClick={() => void onRebuildNow()}>
          <RefreshCw className="h-4 w-4" /> Ricalcola adesso
        </Button>
      </div>
      <JobRunStatus run={rebuildStatus.data} />

      {history.isLoading && <Skeleton className="h-72 w-full" />}
      {history.data && (
        <ChartCard
          title="Patrimonio nel tempo"
          empty={trendPoints.length === 0}
          emptyState={
            <EmptyState
              icon={Landmark}
              title="Nessuno storico ancora"
              description="Lo storico si costruisce giorno per giorno dallo snapshot automatico — usa 'Ricalcola adesso' per crearne subito uno."
            />
          }
          tableCaption="Patrimonio nel tempo"
          tableHeaders={["Data", "Patrimonio"]}
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
              <li>
                <button
                  type="button"
                  onClick={() => setSelectedComposition("liquidity")}
                  className="flex w-full items-center justify-between rounded-md p-1 text-left hover:bg-surface-hover"
                >
                  <span className="text-text">Liquidità</span>
                  <span className="font-numeric text-text">{formatMoney(balances.data.liquidity_total, currency)}</span>
                </button>
              </li>
              {Number(balances.data.debt_total) !== 0 && (
                <li>
                  <button
                    type="button"
                    onClick={() => setSelectedComposition("debt")}
                    className="flex w-full items-center justify-between rounded-md p-1 text-left hover:bg-surface-hover"
                  >
                    <span className="text-text">Debiti</span>
                    <span className="font-numeric text-danger">{formatMoney(balances.data.debt_total, currency)}</span>
                  </button>
                </li>
              )}
              {/* Il saldo dei conti titoli conta gia' come Liquidita' sopra
                  — questa riga e' il valore delle POSIZIONI (asset
                  posseduti), un dato distinto, mai un doppio conteggio.
                  Link diretto invece di un drawer: il breakdown ricco
                  (per tipo di strumento, per asset, PAC vs Investimenti)
                  vive gia' in Investimenti > Allocation, duplicarlo qui
                  sarebbe manutenzione doppia per lo stesso dato. */}
              {balances.data.has_investments && (
                <li>
                  <Link
                    to="/investments?tab=allocation"
                    className="flex items-center justify-between rounded-md p-1 hover:bg-surface-hover"
                  >
                    <span className="text-text">Investimenti</span>
                    <span className="font-numeric text-text">
                      {formatMoney(balances.data.investment_total, currency)}
                    </span>
                  </Link>
                </li>
              )}
              {balances.data.has_investments && (
                <li className="flex items-center justify-between border-t border-border pt-2 font-semibold">
                  <span className="text-text">Patrimonio totale</span>
                  <span className="font-numeric text-text">
                    {formatMoney(
                      Number(balances.data.liquidity_total) +
                        Number(balances.data.debt_total) +
                        Number(balances.data.investment_total),
                      currency,
                    )}
                  </span>
                </li>
              )}
            </ul>
          )}
          {balances.data && !balances.data.has_investments && (
            <EmptyState
              icon={PiggyBank}
              title="Non hai ancora aggiunto investimenti"
              description="Azioni, ETF e obbligazioni appariranno qui non appena registrerai una posizione in Investimenti."
              action={<Link to="/investments" className="text-sm font-medium text-primary hover:underline">Vai a Investimenti</Link>}
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
            I movimenti di investimento (acquisti, vendite, dividendi) sono esclusi da entrate e spese: li trovi
            in Investimenti.
          </p>
        </Card>
      </div>

      <DrillDownDrawer
        open={!!selectedComposition}
        onClose={() => setSelectedComposition(null)}
        title={selectedComposition === "liquidity" ? "Liquidità" : "Debiti"}
        currency={currency}
        isLoading={balances.isLoading || compositionTransactions.isLoading}
        breakdownTitle="Per conto"
        breakdown={compositionAccounts.map((a) => ({
          key: a.financial_account_id,
          label: a.name,
          value: Math.abs(Number(a.balance)),
        }))}
        transactions={(compositionTransactions.data ?? []).map((t) => ({
          id: t.id,
          label: t.merchant ?? t.description_raw,
          date: t.transaction_date,
          amount: t.amount,
          currency: t.currency,
        }))}
        viewAllHref="/accounts"
        viewAllLabel="Vedi tutti i conti"
      />
    </div>
  );
}
