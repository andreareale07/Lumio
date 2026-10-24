import { useState } from "react";
import { AlertTriangle, Landmark, PiggyBank, Wallet } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ChartCard } from "../../components/charts/ChartCard";
import { DrillDownDrawer } from "../../components/charts/DrillDownDrawer";
import { LineComparisonChart, type LineComparisonPoint } from "../../components/charts/LineComparisonChart";
import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { KpiCard } from "../../components/kpi/KpiCard";
import { Button } from "../../components/ui/Button";
import { usePageToolbar } from "../../components/layout/PageToolbarContext";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { JobRunStatus } from "../../components/ui/JobRunStatus";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatMoney, formatPercent, formatPeriodLabel, formatSignedMoney, intlLocale } from "../../lib/format";
import { GRANULARITY_ORDER, periodForAnchor, shiftAnchor, slidingWindow, type Granularity } from "../../lib/period";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import { useTransactionReviewSummary, useTransactions } from "../transactions/api";
import { useAnalyticsCashFlow, useAnalyticsNetWorthHistory, useAnalyticsSummary } from "../analytics/api";
import { formatBucketLabel, greetingBucketForHour } from "../analytics/chartData";
import {
  useSnapshotRebuildStatus,
  useTriggerSnapshotRebuild,
  usePortfolioAllocation,
  usePortfolioValuation,
} from "../portfolio/api";
import { isSignificantChange, median } from "../../lib/stats";

export function DashboardPage() {
  const { t } = useTranslation("dashboard");
  const { granularity, mode, currentPeriod, trendWindow, isAtToday } = usePeriodNavigator({
    granularities: GRANULARITY_ORDER,
  });
  const period = { date_from: currentPeriod.date_from, date_to: currentPeriod.date_to };
  // PHASE 5b (Dashboard come punto d'ingresso): Entrate/Spese forwardano il
  // periodo corrente a /income e /expenses (stesso schema di search param
  // di `usePeriodNavigator`, condiviso da ogni pagina che lo usa) — chi
  // clicca "Entrate" da agosto atterra su Entrate gia' su agosto, non su un
  // default scollegato. Il blocco Patrimonio NON forwarda nulla: e'
  // deliberatamente "a oggi", indipendente dal navigatore.
  const [searchParams] = useSearchParams();
  const periodQuery = searchParams.toString();

  const summary = useAnalyticsSummary(period);
  const cashFlow = useAnalyticsCashFlow({ ...trendWindow, granularity });
  // Segnale "da rivedere" (rework header, PHASE 5b): sostituisce il vecchio
  // blocco "Da fare" a sezione intera — un'icona con contatore in testata,
  // non piu' un blocco proprio (richiesta esplicita dell'utente dopo aver
  // visto la prima versione). Nessun filtro: stesso contatore globale gia'
  // usato da TransactionsPage per il proprio badge.
  const reviewSummary = useTransactionReviewSummary();

  const bucketLabelStrings = {
    locale: intlLocale(),
    quarterAbbrev: t("common:period.quarterAbbrev"),
    semesterAbbrev: t("common:period.semesterAbbrev"),
  };

  const currency = summary.data?.currency ?? "EUR";
  const cashFlowIsEmpty = cashFlow.data?.points.every((p) => p.income === "0" && p.expenses === "0") ?? false;
  const cashFlowPoints = cashFlow.data?.points ?? [];
  const cashFlowGranularity = (cashFlow.data?.granularity ?? "month") as Granularity;

  // --- Blocco PATRIMONIO (stock, "a oggi", ignora il period navigator) ----
  //
  // Vista B (rework Dashboard, PHASE 5, deciso con l'utente dopo mockup a
  // confronto): il patrimonio non ha senso filtrato per periodo, uno stock
  // non e' un flusso — l'unica fonte e' `net-worth-history` (oggi mai
  // chiamata dalla Dashboard), che gia' ritorna liquidita'/debiti/
  // investimenti/patrimonio "come sono ora" via l'ultimo punto della serie,
  // indipendentemente da granularity/anchor del navigator sopra.
  const netWorthHistory = useAnalyticsNetWorthHistory({});
  const netWorthPoints = netWorthHistory.data?.points ?? [];
  const latestNetWorth = netWorthPoints.at(-1);
  const netWorthCurrency = netWorthHistory.data?.currency ?? currency;
  // Bug reale trovato verificando su Docker (workspace appena creato): senza
  // questo, un workspace nuovo non ha ancora nessuno `net_worth_snapshots`
  // (scritto dal cron giornaliero, mai eseguito per un account creato
  // pochi minuti fa) e il blocco Patrimonio resta silenziosamente vuoto,
  // senza errore ne' empty state — stesso gap gia' risolto per lo storico
  // di `NetWorthPage.tsx`, stesso rimedio: azione "Ricalcola adesso" sullo
  // stesso endpoint gia' esistente (`POST /portfolios/snapshots/rebuild`),
  // nessun nuovo endpoint.
  const rebuildSnapshot = useTriggerSnapshotRebuild();
  const rebuildStatus = useSnapshotRebuildStatus();
  const rebuildRunning = rebuildStatus.data?.status === "running";
  const onRebuildNetWorth = async () => {
    await rebuildSnapshot.mutateAsync();
    void rebuildStatus.refetch();
    setTimeout(() => void netWorthHistory.refetch(), 1500);
  };

  const thirtyDaysAgoIso = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const netWorth30dAgo = [...netWorthPoints].reverse().find((p) => p.snapshot_date <= thirtyDaysAgoIso);
  const netWorthDelta30d =
    latestNetWorth && netWorth30dAgo ? Number(latestNetWorth.net_worth) - Number(netWorth30dAgo.net_worth) : undefined;

  // Baseline fissa a 6 mesi COMPLETI (ancorata al mese scorso, esclude
  // sempre il mese corrente parziale) — riusata sia per il tasso di
  // risparmio/mesi di autonomia (Patrimonio) sia per il confronto "vs mese
  // tipico" delle KPI di flusso sotto. Indipendente dal granularity scelto
  // nel navigator per costruzione (§ piano di sessione).
  const baselineWindow = slidingWindow("month", shiftAnchor("month", new Date(), -1), 6);
  const baselineCashFlow = useAnalyticsCashFlow({ ...baselineWindow, granularity: "month" });
  // Bug reale trovato controllando i dati veri di un utente: un mese con
  // entrate E spese entrambe a zero quasi sempre non significa "quel mese
  // non ha speso nulla" — significa che quel mese e' precedente al primo
  // movimento importato (nessun dato ancora, non "spesa zero"). Trattarlo
  // come uno zero vero abbassa artificialmente la mediana: con un conto le
  // cui transazioni iniziano a maggio, la finestra fissa a 6 mesi (feb-lug)
  // conta 3 mesi fantasma a zero, portando "mesi di autonomia" da un valore
  // reale di ~2,3 a un fasullo "5" (mediana spese 174€ invece di ~374€).
  // Si escludono quindi dalla base di calcolo i mesi senza ALCUN dato.
  const baselinePointsWithData = (baselineCashFlow.data?.points ?? []).filter(
    (p) => Number(p.income) !== 0 || Number(p.expenses) !== 0,
  );
  const baselineIncomeValues = baselinePointsWithData.map((p) => Number(p.income));
  const baselineExpensesValues = baselinePointsWithData.map((p) => Number(p.expenses));
  const baselineNetValues = baselinePointsWithData.map((p) => Number(p.net));
  const medianMonthlyExpenses = median(baselineExpensesValues);
  const medianMonthlyIncome = median(baselineIncomeValues);
  const medianMonthlyNet = median(baselineNetValues);

  const currentLiquidity = latestNetWorth ? Number(latestNetWorth.liquidity) : undefined;
  const runwayMonths =
    currentLiquidity !== undefined && medianMonthlyExpenses > 0 ? currentLiquidity / medianMonthlyExpenses : undefined;
  const runwayNote =
    currentLiquidity === undefined
      ? t("stock.runway.notAvailable")
      : medianMonthlyNet >= 0
        ? t("stock.runway.accumulating")
        : runwayMonths !== undefined
          ? t("stock.runway.months", { count: Math.round(runwayMonths) })
          : t("stock.runway.notAvailable");

  // --- Blocco FLUSSO (filtrato dal period navigator, invariato) -----------
  const income = summary.data ? Number(summary.data.income) : undefined;
  const expenses = summary.data ? Number(summary.data.expenses) : undefined;
  const savingsRate =
    income !== undefined && expenses !== undefined && Math.abs(income) > 0.01 ? (income - expenses) / income : undefined;

  const isMonthGranularity = mode === "granular" && granularity === "month";
  const isCurrentMonth = isMonthGranularity && isAtToday;
  const now = new Date();
  const elapsedDaysInMonth = now.getDate();
  const totalDaysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const isPartialMonth = isCurrentMonth && elapsedDaysInMonth < totalDaysInMonth;
  const suppressComparisonForYoungMonth = isCurrentMonth && elapsedDaysInMonth < 5;

  const comparisonLabel = summary.data
    ? t("kpi.comparisonLabel", {
        period: formatPeriodLabel(summary.data.comparison_period.date_from, summary.data.comparison_period.date_to),
      })
    : undefined;

  /** Decide se una KPI di flusso mostra la freccia colorata (vs mediana 6
   * mesi) o un testo neutro — SOLO quando si guarda il mese come
   * granularita' (§ piano: trimestre/anno restano sul confronto esistente
   * "vs periodo precedente", nessuna baseline a mediana per loro in questa
   * fase). */
  function monthComparison(current: number | undefined, baselineMedian: number) {
    if (current === undefined) return { previousValue: undefined, note: undefined };
    if (suppressComparisonForYoungMonth) return { previousValue: undefined, note: t("flow.tooEarlyForComparison") };
    if (!isSignificantChange(current, baselineMedian)) {
      return { previousValue: undefined, note: t("flow.inLineWithTypical") };
    }
    return { previousValue: String(baselineMedian), note: undefined };
  }

  const incomeComparison = isMonthGranularity
    ? monthComparison(income, medianMonthlyIncome)
    : { previousValue: summary.data?.previous_income, note: undefined };
  const expensesComparison = isMonthGranularity
    ? monthComparison(expenses, medianMonthlyExpenses)
    : { previousValue: summary.data?.previous_expenses, note: undefined };
  const netCashFlowValue = summary.data ? Number(summary.data.net_cash_flow) : undefined;
  const netCashFlowComparison = isMonthGranularity
    ? monthComparison(netCashFlowValue, medianMonthlyNet)
    : { previousValue: summary.data?.previous_net_cash_flow, note: undefined };
  const flowComparisonLabel = isMonthGranularity ? t("flow.vsTypicalMonth") : comparisonLabel;

  // Drill-down periodo (click su un punto Entrate/Uscite): un bucket
  // temporale non ha "categorie", solo il confronto entrate/uscite di
  // QUEL periodo + le transazioni che ci sono cadute dentro.
  const [selectedBucket, setSelectedBucket] = useState<LineComparisonPoint | null>(null);
  const bucketRange = selectedBucket ? periodForAnchor(cashFlowGranularity, new Date(selectedBucket.period)) : null;
  const bucketTransactions = useTransactions(
    { date_from: bucketRange?.date_from, date_to: bucketRange?.date_to, limit: 5 },
    { enabled: !!selectedBucket },
  );

  const periodNav = <PeriodNavigator granularities={GRANULARITY_ORDER} />;
  const toolbarPortal = usePageToolbar(periodNav);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      {toolbarPortal}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">
            {t(`greeting.${greetingBucketForHour(new Date().getHours())}`)}
          </h1>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-text-muted">{t("subtitle")}</p>
            {!!reviewSummary.data?.needs_review && (
              <Link
                to="/transactions?review=1"
                title={t("attention.needsReview", { count: reviewSummary.data.needs_review })}
                aria-label={t("attention.needsReview", { count: reviewSummary.data.needs_review })}
                className="inline-flex items-center gap-1 rounded-full bg-warning-bg px-2 py-0.5 text-xs font-medium text-warning hover:opacity-90"
              >
                <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                {reviewSummary.data.needs_review}
              </Link>
            )}
          </div>
        </div>
        <div className="md:hidden">{periodNav}</div>
      </div>

      {/* --- PATRIMONIO: stock, sempre "a oggi", ignora il navigator --- */}
      <section className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-text">{t("stock.sectionTitle")}</h2>
          <span className="text-xs text-text-muted">{t("stock.asOfToday")}</span>
        </div>

        {netWorthHistory.isError && (
          <ErrorState message={t("loadError")} onRetry={() => void netWorthHistory.refetch()} />
        )}
        {netWorthHistory.isLoading && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        )}
        {netWorthHistory.data && netWorthPoints.length === 0 && (
          <EmptyState
            icon={Landmark}
            title={t("stock.empty.title")}
            description={t("stock.empty.description")}
            action={
              <div className="flex flex-col items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  loading={rebuildSnapshot.isPending}
                  disabled={rebuildRunning}
                  onClick={() => void onRebuildNetWorth()}
                >
                  {t("analytics:netWorth.rebuildNow")}
                </Button>
                {rebuildRunning && <JobRunStatus run={rebuildStatus.data} />}
              </div>
            }
          />
        )}
        {latestNetWorth && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <KpiCard
              title={t("kpi.netWorth")}
              value={latestNetWorth.net_worth}
              currency={netWorthCurrency}
              href="/net-worth"
              hideArrow
              note={
                netWorthDelta30d !== undefined
                  ? t("stock.netWorthDelta", { amount: formatSignedMoney(netWorthDelta30d, netWorthCurrency) })
                  : undefined
              }
            />
            <KpiCard
              title={t("kpi.liquidity")}
              value={latestNetWorth.liquidity}
              currency={netWorthCurrency}
              href="/net-worth"
              hideArrow
              note={runwayNote}
            />
            <KpiCard
              title={t("kpi.debt")}
              value={latestNetWorth.debt}
              currency={netWorthCurrency}
              href="/net-worth"
              hideArrow
              positiveIsGood={false}
              note={t("kpi.debtNote")}
            />
          </div>
        )}
      </section>

      {/* --- FLUSSO DEL PERIODO: filtrato dal period navigator --- */}
      <section className="flex flex-col gap-4">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-text">{t("flow.sectionTitle")}</h2>
          {isPartialMonth && (
            <span className="text-xs text-text-muted">
              {t("flow.partialMonth", { elapsed: elapsedDaysInMonth, total: totalDaysInMonth })}
            </span>
          )}
        </div>

        {summary.isError && <ErrorState message={t("loadError")} onRetry={() => void summary.refetch()} />}
        {summary.isLoading && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        )}
        {summary.data && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard
              title={t("kpi.income")}
              value={summary.data.income}
              previousValue={incomeComparison.previousValue}
              comparisonLabel={flowComparisonLabel}
              note={incomeComparison.note}
              currency={currency}
              href={periodQuery ? `/income?${periodQuery}` : "/income"}
              hideArrow
            />
            <KpiCard
              title={t("kpi.expenses")}
              value={summary.data.expenses}
              previousValue={expensesComparison.previousValue}
              comparisonLabel={flowComparisonLabel}
              note={expensesComparison.note}
              currency={currency}
              positiveIsGood={false}
              href={periodQuery ? `/expenses?${periodQuery}` : "/expenses"}
              hideArrow
            />
            <KpiCard
              title={t("kpi.cashFlow")}
              value={summary.data.net_cash_flow}
              previousValue={netCashFlowComparison.previousValue}
              comparisonLabel={flowComparisonLabel}
              note={netCashFlowComparison.note}
              currency={currency}
            />
            <div className="flex flex-col gap-1">
              <span className="text-sm text-text-muted">{t("flow.savingsRate.title")}</span>
              <span
                className={`font-numeric text-2xl font-semibold ${
                  savingsRate === undefined ? "text-text" : savingsRate >= 0 ? "text-success" : "text-danger"
                }`}
              >
                {savingsRate !== undefined
                  ? formatPercent(savingsRate, { signed: true })
                  : t("flow.savingsRate.notAvailable")}
              </span>
            </div>
          </div>
        )}

        {cashFlow.isLoading && <Skeleton className="h-72 w-full" />}
        {cashFlow.isError && (
          <ErrorState message={t("cashFlowChart.chartError")} onRetry={() => void cashFlow.refetch()} />
        )}
        {cashFlow.data && (
          <ChartCard
            title={t("cashFlowChart.title")}
            subtitle={formatPeriodLabel(cashFlow.data.period.date_from, cashFlow.data.period.date_to)}
            empty={cashFlowIsEmpty}
            emptyState={
              <EmptyState
                icon={Wallet}
                title={t("cashFlowChart.empty.title")}
                description={t("cashFlowChart.empty.description")}
                action={
                  <LinkButton to="/imports" size="sm">
                    {t("cashFlowChart.empty.action")}
                  </LinkButton>
                }
              />
            }
            tableCaption={t("cashFlowChart.tableCaption")}
            tableHeaders={t("cashFlowChart.tableHeaders", { returnObjects: true }) as string[]}
            tableRows={cashFlowPoints.map((p) => [
              formatBucketLabel(p.period, cashFlowGranularity, bucketLabelStrings),
              formatMoney(p.income, currency),
              formatMoney(p.expenses, currency),
            ])}
          >
            <LineComparisonChart
              currency={currency}
              data={cashFlowPoints.map((p) => ({
                period: p.period,
                label: formatBucketLabel(p.period, cashFlowGranularity, bucketLabelStrings),
                income: Number(p.income),
                expenses: Number(p.expenses),
              }))}
              series={[
                { key: "income", label: t("common:cashFlow.income"), tone: "success" },
                { key: "expenses", label: t("common:cashFlow.expenses"), tone: "danger" },
              ]}
              onPointClick={setSelectedBucket}
            />
          </ChartCard>
        )}
      </section>

      {/* Il saldo dei conti titoli conta gia' come Liquidita' (sono spesso
          ibridi: spendibili con carta E usati per investire, es. Trade
          Republic/Fineco) — questo widget mostra il valore delle
          POSIZIONI (asset posseduti), un dato distinto dal cash, mai
          doppio conteggio (M09b). */}
      <PortfolioWidget />

      <DrillDownDrawer
        open={!!selectedBucket}
        onClose={() => setSelectedBucket(null)}
        title={selectedBucket?.label ?? ""}
        currency={currency}
        isLoading={bucketTransactions.isLoading}
        breakdownTitle={t("bucketDrawer.breakdownTitle")}
        breakdown={
          selectedBucket
            ? [
                { key: "income", label: t("bucketDrawer.income"), value: Number(selectedBucket.income) },
                { key: "expenses", label: t("bucketDrawer.expenses"), value: Number(selectedBucket.expenses) },
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
  const { t } = useTranslation("dashboard");
  const valuation = usePortfolioValuation(null);
  const allocation = usePortfolioAllocation(null);

  if (valuation.isLoading) {
    return (
      <Card className="flex flex-col gap-2">
        <Skeleton className="h-24 w-full" />
      </Card>
    );
  }
  if (valuation.isError) {
    return (
      <Card className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-text">{t("portfolioWidget.title")}</h3>
        <ErrorState message={t("portfolioWidget.loadError")} onRetry={() => void valuation.refetch()} />
      </Card>
    );
  }

  const data = valuation.data;
  if (!data || !data.has_holdings) {
    return (
      <Card className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-text">{t("portfolioWidget.title")}</h3>
        <EmptyState
          icon={PiggyBank}
          title={t("portfolioWidget.empty.title")}
          description={t("portfolioWidget.empty.description")}
          action={
            <LinkButton to="/investments" size="sm">
              {t("portfolioWidget.goToInvestments")}
            </LinkButton>
          }
        />
      </Card>
    );
  }

  const costBasis = Number(data.cost_basis);
  const performancePct = costBasis !== 0 ? Number(data.unrealized_pl) / costBasis : 0;
  const topAllocation = allocation.data?.by_asset_type.slice(0, 4) ?? [];

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-text">{t("portfolioWidget.title")}</h3>
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
        <Link to="/investments" className="text-sm font-medium text-primary hover:underline">
          {t("portfolioWidget.goToInvestments")}
        </Link>
      </div>
      {topAllocation.length > 0 && (
        <ul className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {topAllocation.map((item) => (
            <li key={item.key} className="flex items-center gap-1.5 text-text-muted">
              <span>{item.label}</span>
              <span className="font-numeric text-text">{formatPercent(item.share)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
