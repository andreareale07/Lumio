import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { History, Landmark, PiggyBank, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DrillDownDrawer } from "../../components/charts/DrillDownDrawer";
import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { usePageToolbar } from "../../components/layout/PageToolbarContext";
import { BackLink } from "../../components/ui/BackLink";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { JobRunStatus } from "../../components/ui/JobRunStatus";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatDate, formatMoney } from "../../lib/format";
import { GRANULARITY_ORDER } from "../../lib/period";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import { useTransactions } from "../transactions/api";
import {
  useSnapshotBackfillStatus,
  useSnapshotRebuildStatus,
  useTriggerSnapshotBackfill,
  useTriggerSnapshotRebuild,
} from "../portfolio/api";
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
  const { t } = useTranslation(["analytics", "dashboard"]);
  const { currentPeriod, trendWindow } = usePeriodNavigator({
    granularities: GRANULARITY_ORDER,
  });

  const summary = useAnalyticsSummary({ date_from: currentPeriod.date_from, date_to: currentPeriod.date_to });
  const balances = useAnalyticsBalances();
  const history = useAnalyticsNetWorthHistory({ date_from: trendWindow.date_from, date_to: trendWindow.date_to });
  const rebuildSnapshot = useTriggerSnapshotRebuild();
  const rebuildStatus = useSnapshotRebuildStatus();
  const backfillSnapshot = useTriggerSnapshotBackfill();
  const backfillStatus = useSnapshotBackfillStatus();
  const queryClient = useQueryClient();

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

  // Storico patrimonio ricostruito (FETTA 3): a differenza di "Ricalcola
  // adesso" (secondi, setTimeout va bene), questo job puo' impiegare
  // minuti/ore — un timeout fisso non ha senso. Si invalida la query dello
  // storico solo quando lo stato persistente passa OSSERVABILMENTE da
  // 'running' a 'success' (polling gia' attivo via useSnapshotBackfillStatus),
  // non ad ogni render/poll.
  const previousBackfillStatusRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    const previousStatus = previousBackfillStatusRef.current;
    const currentStatus = backfillStatus.data?.status;
    if (previousStatus === "running" && currentStatus === "success") {
      void queryClient.invalidateQueries({ queryKey: ["analytics", "net-worth-history"] });
    }
    previousBackfillStatusRef.current = currentStatus;
  }, [backfillStatus.data?.status, queryClient]);

  const onBackfillHistory = async () => {
    await backfillSnapshot.mutateAsync();
    void backfillStatus.refetch();
  };

  const periodNav = <PeriodNavigator granularities={GRANULARITY_ORDER} />;
  const backfillButton = (
    <Button
      variant="secondary"
      size="sm"
      loading={backfillSnapshot.isPending}
      onClick={() => void onBackfillHistory()}
    >
      <History className="h-4 w-4" /> {t("netWorth.backfillHistory")}
    </Button>
  );
  const rebuildButton = (
    <Button variant="secondary" size="sm" loading={rebuildSnapshot.isPending} onClick={() => void onRebuildNow()}>
      <RefreshCw className="h-4 w-4" /> {t("netWorth.rebuildNow")}
    </Button>
  );
  // Navigatore periodo + le due azioni di ricalcolo vivono nel Topbar
  // (desktop) e in righe `md:hidden` qui sotto per mobile — stesso
  // portal/duplicazione-per-breakpoint gia' in uso altrove.
  const toolbarPortal = usePageToolbar(
    <>
      {periodNav}
      {backfillButton}
      {rebuildButton}
    </>,
  );

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      {toolbarPortal}
      <BackLink to="/" label={t("navigation:items.dashboard")} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">{t("netWorth.title")}</h1>
          {summary.data && (
            <span className="font-numeric text-2xl font-semibold text-text">
              {formatMoney(summary.data.net_worth, currency)}
            </span>
          )}
          <p className="text-sm text-text-muted">{t("netWorth.subtitle")}</p>
        </div>
        <div className="md:hidden">{periodNav}</div>
      </div>

      {summary.isError && <ErrorState message={t("netWorth.errorMessage")} onRetry={() => void summary.refetch()} />}

      <div className="flex flex-wrap items-center justify-end gap-2 md:hidden">
        {backfillButton}
        {rebuildButton}
      </div>
      <JobRunStatus run={backfillStatus.data} />
      <JobRunStatus run={rebuildStatus.data} />

      {history.isLoading && <Skeleton className="h-72 w-full" />}
      {history.data && (
        <ChartCard
          title={t("netWorth.history.title")}
          empty={trendPoints.length === 0}
          emptyState={
            <EmptyState
              icon={Landmark}
              title={t("netWorth.history.emptyTitle")}
              description={t("netWorth.history.emptyDescription")}
              action={
                <Button size="sm" loading={backfillSnapshot.isPending} onClick={() => void onBackfillHistory()}>
                  <History className="h-4 w-4" /> {t("netWorth.backfillHistory")}
                </Button>
              }
            />
          }
          tableCaption={t("netWorth.history.tableCaption")}
          tableHeaders={t("netWorth.history.tableHeaders", { returnObjects: true }) as string[]}
          tableRows={trendPoints.map((p) => [p.label, formatMoney(p.value, currency)])}
        >
          <AreaTrendChart data={trendPoints} currency={currency} />
        </ChartCard>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">{t("netWorth.composition.title")}</h3>
          {balances.isLoading && <Skeleton className="h-24 w-full" />}
          {balances.data && (
            <ul className="flex flex-col gap-2 text-sm">
              <li>
                <button
                  type="button"
                  onClick={() => setSelectedComposition("liquidity")}
                  className="flex w-full items-center justify-between rounded-md p-1 text-left hover:bg-surface-hover"
                >
                  <span className="text-text">{t("dashboard:kpi.liquidity")}</span>
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
                    <span className="text-text">{t("dashboard:kpi.debt")}</span>
                    <span className="font-numeric text-danger">{formatMoney(balances.data.debt_total, currency)}</span>
                  </button>
                </li>
              )}
              {/* Il saldo dei conti titoli conta gia' come Liquidita' sopra
                  — questa riga e' il valore delle POSIZIONI (asset
                  posseduti), un dato distinto, mai un doppio conteggio.
                  Link diretto invece di un drawer: la composizione (per
                  tipo di asset, per valuta) e' gia' visibile in cima alla
                  Panoramica Investimenti, duplicarla qui sarebbe
                  manutenzione doppia per lo stesso dato. */}
              {balances.data.has_investments && (
                <li>
                  <Link
                    to="/investments"
                    className="flex items-center justify-between rounded-md p-1 hover:bg-surface-hover"
                  >
                    <span className="text-text">{t("dashboard:kpi.investments")}</span>
                    <span className="font-numeric text-text">
                      {formatMoney(balances.data.investment_total, currency)}
                    </span>
                  </Link>
                </li>
              )}
              {balances.data.has_investments && (
                <li className="flex items-center justify-between border-t border-border pt-2 font-semibold">
                  <span className="text-text">{t("dashboard:kpi.netWorth")}</span>
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
              title={t("dashboard:portfolioWidget.empty.title")}
              description={t("netWorth.composition.noInvestmentsDescription")}
              action={
                <Link to="/investments" className="text-sm font-medium text-primary hover:underline">
                  {t("dashboard:portfolioWidget.goToInvestments")}
                </Link>
              }
            />
          )}
        </Card>

        <Card className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">{t("netWorth.periodChange.title")}</h3>
          {summary.data && (
            <ul className="flex flex-col gap-2 text-sm">
              <li className="flex items-center justify-between">
                <span className="text-text">{t("dashboard:kpi.income")}</span>
                <span className="font-numeric text-success">+{formatMoney(summary.data.income, currency)}</span>
              </li>
              <li className="flex items-center justify-between">
                <span className="text-text">{t("dashboard:kpi.expenses")}</span>
                <span className="font-numeric text-danger">-{formatMoney(summary.data.expenses, currency)}</span>
              </li>
              <li className="flex items-center justify-between border-t border-border pt-2 font-semibold">
                <span className="text-text">{t("netWorth.periodChange.total")}</span>
                <span className="font-numeric text-text">
                  {Number(summary.data.net_cash_flow) >= 0 ? "+" : ""}
                  {formatMoney(summary.data.net_cash_flow, currency)}
                </span>
              </li>
            </ul>
          )}
          <p className="text-sm text-text-muted">{t("netWorth.periodChange.investmentNote")}</p>
        </Card>
      </div>

      <DrillDownDrawer
        open={!!selectedComposition}
        onClose={() => setSelectedComposition(null)}
        title={selectedComposition === "liquidity" ? t("dashboard:kpi.liquidity") : t("dashboard:kpi.debt")}
        currency={currency}
        isLoading={balances.isLoading || compositionTransactions.isLoading}
        breakdownTitle={t("netWorth.composition.breakdownTitle")}
        breakdown={compositionAccounts.map((a) => ({
          key: a.financial_account_id,
          label: a.name,
          value: Math.abs(Number(a.balance)),
        }))}
        transactions={(compositionTransactions.data ?? []).map((txn) => ({
          id: txn.id,
          label: txn.merchant ?? txn.description_raw,
          date: txn.transaction_date,
          amount: txn.amount,
          currency: txn.currency,
        }))}
        viewAllHref="/accounts"
        viewAllLabel={t("netWorth.composition.viewAllAccounts")}
      />
    </div>
  );
}
