import { useState } from "react";
import { Landmark, Wallet } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { BarComparisonChart } from "../../components/charts/BarComparisonChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DonutChart } from "../../components/charts/DonutChart";
import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { usePageToolbar } from "../../components/layout/PageToolbarContext";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { Skeleton, SkeletonRows } from "../../components/ui/Skeleton";
import { Tabs } from "../../components/ui/Tabs";
import { formatDate, formatMoney, formatPeriodLabel, formatSignedMoney, intlLocale } from "../../lib/format";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import {
  useAnalyticsBalanceHistory,
  useAnalyticsBalances,
  useAnalyticsByCategory,
  useAnalyticsCashFlow,
} from "../analytics/api";
import { formatBucketLabel } from "../analytics/chartData";
import { useTransactions } from "../transactions/api";
import { Badge } from "../../components/ui/Badge";
import { useLossPocket, useResolveTaxRegime, useTaxRegimePeriods } from "../tax/api";
import { useTaxRegimeLabel } from "../tax/labels";
import { TaxCodeBadge } from "../tax/TaxCodeBadge";
import { AccountDeleteDialog } from "./AccountDeleteDialog";
import { useAccounts } from "./api";
import { useAccountTypeLabel } from "./labels";

export function AccountDetailPage() {
  const { t } = useTranslation("accounts");
  const accountTypeLabel = useAccountTypeLabel();
  const navigate = useNavigate();
  const { t: tTax } = useTranslation("tax");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const { accountId } = useParams<{ accountId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") ?? "overview";

  const setTab = (next: string) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params);
  };

  const { data: accounts, isLoading, isError, refetch } = useAccounts();
  const account = accounts?.find((a) => a.id === accountId);
  const balances = useAnalyticsBalances();
  const accountBalance = balances.data?.accounts.find((a) => a.financial_account_id === accountId);

  if (isLoading) return <SkeletonRows rows={4} />;
  if (isError) {
    return <ErrorState message={t("detail.loadError")} onRetry={() => void refetch()} />;
  }
  if (!account || !accountId) {
    return (
      <EmptyState
        icon={Landmark}
        title={t("detail.notFound.title")}
        description={t("detail.notFound.description")}
        action={
          <LinkButton to="/accounts" size="sm">
            {t("detail.notFound.action")}
          </LinkButton>
        }
      />
    );
  }

  // Nessun filtro per account_type (vedi AccountEditPage): un conto
  // "checking" puo' comunque essere un conto titoli in pratica.
  const TABS = [
    { key: "overview", label: t("detail.tabs.overview") },
    { key: "transactions", label: t("detail.tabs.transactions") },
    { key: "analytics", label: t("detail.tabs.analytics") },
    { key: "tax", label: tTax("account.tab.title") },
  ];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-text">{account.name}</h1>
          <p className="text-sm text-text-muted">
            {accountTypeLabel(account.account_type)} · {account.currency}
          </p>
          <AccountTaxRegimeBadge accountId={account.id} />
        </div>
        <div className="flex items-center gap-3">
          {accountBalance && (
            <span className="font-numeric text-2xl font-semibold text-text">
              {formatMoney(accountBalance.balance, account.currency)}
            </span>
          )}
          <LinkButton to={`/accounts/${account.id}/edit`} variant="secondary" size="sm">
            {t("page.edit")}
          </LinkButton>
          <button
            type="button"
            onClick={() => setDeleteOpen(true)}
            className="text-sm text-danger hover:underline"
          >
            {t("page.delete")}
          </button>
        </div>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" && <AccountOverviewTab accountId={accountId} onSeeAll={() => setTab("transactions")} />}
      {tab === "transactions" && <AccountTransactionsTab accountId={accountId} />}
      {tab === "analytics" && <AccountAnalyticsTab accountId={accountId} currency={account.currency} />}
      {tab === "tax" && <AccountTaxTab accountId={account.id} />}

      <AccountDeleteDialog
        account={deleteOpen ? account : null}
        onClose={(deleted?: boolean) => {
          setDeleteOpen(false);
          if (deleted) navigate("/accounts");
        }}
      />
    </div>
  );
}

function AccountOverviewTab({ accountId, onSeeAll }: { accountId: string; onSeeAll: () => void }) {
  const { t } = useTranslation("accounts");
  const recent = useTransactions({ financial_account_id: accountId, limit: 5 });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text">{t("detail.overview.recentTransactions")}</h3>
        <button type="button" onClick={onSeeAll} className="text-sm font-medium text-primary hover:underline">
          {t("detail.overview.seeAll")}
        </button>
      </div>
      {recent.isLoading && <SkeletonRows rows={4} />}
      {recent.isError && (
        <ErrorState message={t("detail.overview.transactionsError")} onRetry={() => void recent.refetch()} />
      )}
      {recent.data && recent.data.length === 0 && (
        <EmptyState
          icon={Wallet}
          title={t("detail.overview.empty.title")}
          description={t("detail.overview.empty.description")}
        />
      )}
      {recent.data && recent.data.length > 0 && (
        <div className="flex flex-col gap-2">
          {recent.data.map((transaction) => (
            <div
              key={transaction.id}
              className="flex items-center justify-between rounded-lg border border-border bg-surface p-3 text-sm"
            >
              <div className="flex flex-col">
                <span className="text-text">{transaction.merchant ?? transaction.description_raw}</span>
                <span className="text-text-muted">{formatDate(transaction.transaction_date)}</span>
              </div>
              <span className="font-numeric text-text">
                {formatSignedMoney(transaction.amount, transaction.currency)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AccountTransactionsTab({ accountId }: { accountId: string }) {
  const { t } = useTranslation("accounts");
  const PAGE_SIZE = 25;
  const [offset, setOffset] = useState(0);
  const { data: transactions, isLoading, isError, refetch } = useTransactions({
    financial_account_id: accountId,
    limit: PAGE_SIZE,
    offset,
  });

  return (
    <div className="flex flex-col gap-3">
      {isLoading && <SkeletonRows rows={6} />}
      {isError && <ErrorState message={t("detail.transactionsTab.error")} onRetry={() => void refetch()} />}
      {transactions && transactions.length === 0 && (
        <EmptyState
          icon={Wallet}
          title={t("detail.transactionsTab.empty.title")}
          description={t("detail.transactionsTab.empty.description")}
        />
      )}
      {transactions && transactions.length > 0 && (
        <div className="flex flex-col gap-2">
          {transactions.map((transaction) => (
            <div
              key={transaction.id}
              className="flex items-center justify-between rounded-lg border border-border bg-surface p-3 text-sm"
            >
              <div className="flex flex-col">
                <span className="text-text">{transaction.merchant ?? transaction.description_raw}</span>
                <span className="text-text-muted">{formatDate(transaction.transaction_date)}</span>
              </div>
              <span className="font-numeric text-text">
                {formatSignedMoney(transaction.amount, transaction.currency)}
              </span>
            </div>
          ))}
          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="text-sm text-text-muted disabled:opacity-40"
            >
              {t("detail.transactionsTab.previous")}
            </button>
            <button
              type="button"
              disabled={transactions.length < PAGE_SIZE}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="text-sm text-text-muted disabled:opacity-40"
            >
              {t("detail.transactionsTab.next")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function AccountAnalyticsTab({ accountId, currency }: { accountId: string; currency: string }) {
  const { t } = useTranslation("accounts");
  const { granularity: navGranularity, currentPeriod, trendWindow } = usePeriodNavigator({
    granularities: ["month", "quarter", "year"],
  });
  const period = { date_from: currentPeriod.date_from, date_to: currentPeriod.date_to, financial_account_id: accountId };
  const trendPeriod = { ...trendWindow, financial_account_id: accountId };

  const history = useAnalyticsBalanceHistory({ ...trendPeriod, granularity: navGranularity });
  const cashFlow = useAnalyticsCashFlow({ ...trendPeriod, granularity: navGranularity });
  const byCategory = useAnalyticsByCategory({ ...period, direction: "expense" });

  const bucketLabelStrings = {
    locale: intlLocale(),
    quarterAbbrev: t("common:period.quarterAbbrev"),
    semesterAbbrev: t("common:period.semesterAbbrev"),
  };

  const historyGranularity = history.data?.granularity ?? "month";
  const trendPoints = (history.data?.points ?? []).map((p) => ({
    period: p.period,
    label: formatBucketLabel(p.period, historyGranularity, bucketLabelStrings),
    value: Number(p.balance),
  }));

  const cashFlowGranularity = cashFlow.data?.granularity ?? "month";
  const cashFlowBars = (cashFlow.data?.points ?? []).map((p) => ({
    period: p.period,
    label: formatBucketLabel(p.period, cashFlowGranularity, bucketLabelStrings),
    income: Number(p.income),
    expenses: Number(p.expenses),
  }));

  const periodNav = <PeriodNavigator granularities={["month", "quarter", "year"]} />;
  const toolbarPortal = usePageToolbar(periodNav);

  return (
    <div className="flex flex-col gap-4">
      {toolbarPortal}
      <div className="md:hidden">{periodNav}</div>

      {history.isLoading && <Skeleton className="h-64 w-full" />}
      {history.data && (
        <ChartCard
          title={t("detail.analyticsTab.balanceChart.title")}
          subtitle={formatPeriodLabel(history.data.period.date_from, history.data.period.date_to)}
          empty={trendPoints.length === 0}
          emptyState={
            <EmptyState
              icon={Landmark}
              title={t("detail.analyticsTab.balanceChart.empty")}
              description={t("detail.analyticsTab.balanceChart.emptyDescription")}
            />
          }
          tableCaption={t("detail.analyticsTab.balanceChart.tableCaption")}
          tableHeaders={t("detail.analyticsTab.balanceChart.tableHeaders", { returnObjects: true }) as string[]}
          tableRows={trendPoints.map((p) => [p.label, formatMoney(p.value, currency)])}
        >
          <AreaTrendChart data={trendPoints} currency={currency} valueLabel={t("detail.analyticsTab.balanceChart.valueLabel")} />
        </ChartCard>
      )}

      {cashFlow.isLoading && <Skeleton className="h-64 w-full" />}
      {cashFlow.data && (
        <ChartCard
          title={t("detail.analyticsTab.cashFlowChart.title")}
          empty={cashFlowBars.every((p) => p.income === 0 && p.expenses === 0)}
          emptyState={
            <EmptyState
              icon={Wallet}
              title={t("detail.analyticsTab.cashFlowChart.empty")}
              description={t("detail.analyticsTab.cashFlowChart.emptyDescription")}
            />
          }
          tableCaption={t("detail.analyticsTab.cashFlowChart.tableCaption")}
          tableHeaders={t("detail.analyticsTab.cashFlowChart.tableHeaders", { returnObjects: true }) as string[]}
          tableRows={cashFlow.data.points.map((p) => [
            formatBucketLabel(p.period, cashFlowGranularity, bucketLabelStrings),
            formatMoney(p.income, currency),
            formatMoney(p.expenses, currency),
          ])}
        >
          <BarComparisonChart
            data={cashFlowBars}
            currency={currency}
            incomeLabel={t("common:cashFlow.income")}
            expensesLabel={t("common:cashFlow.expenses")}
          />
        </ChartCard>
      )}

      {byCategory.isLoading && <Skeleton className="h-64 w-full" />}
      {byCategory.data && (
        <ChartCard
          title={t("detail.analyticsTab.byCategoryChart.title")}
          empty={byCategory.data.items.length === 0}
          emptyState={
            <EmptyState
              icon={Landmark}
              title={t("detail.analyticsTab.byCategoryChart.empty")}
              description={t("detail.analyticsTab.byCategoryChart.emptyDescription")}
            />
          }
          tableCaption={t("detail.analyticsTab.byCategoryChart.tableCaption")}
          tableHeaders={t("detail.analyticsTab.byCategoryChart.tableHeaders", { returnObjects: true }) as string[]}
          tableRows={byCategory.data.items.map((item) => [item.name, formatMoney(item.total, currency)])}
        >
          <DonutChart
            currency={currency}
            data={byCategory.data.items.map((item) => ({ label: item.name, value: Number(item.total) }))}
          />
        </ChartCard>
      )}
    </div>
  );
}

function AccountTaxRegimeBadge({ accountId }: { accountId: string }) {
  const regimeLabel = useTaxRegimeLabel();
  const { t } = useTranslation("tax");
  const today = new Date().toISOString().slice(0, 10);
  const resolved = useResolveTaxRegime(accountId, today);
  if (!resolved.data?.regime_code) return null;
  return (
    <div className="mt-1">
      <Badge tone="primary">
        <TaxCodeBadge value={regimeLabel(resolved.data.regime_code)} />
      </Badge>
      <span className="ml-1 text-xs text-text-muted">{t("account.tab.currentRegime")}</span>
    </div>
  );
}

function AccountTaxTab({ accountId }: { accountId: string }) {
  const { t } = useTranslation("tax");
  const today = new Date().toISOString().slice(0, 10);
  const { data: periods } = useTaxRegimePeriods(accountId);
  const regimeLabel = useTaxRegimeLabel();
  const pocket = useLossPocket(today);
  const accountTotal = pocket.data?.totals_by_perimeter[accountId] ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-surface p-4">
        <h3 className="text-sm font-semibold text-text">{t("account.tab.periodsTitle")}</h3>
        {(!periods || periods.length === 0) && (
          <p className="mt-2 text-sm text-text-muted">{t("account.tab.noRegime")}</p>
        )}
        {periods && periods.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {periods
              .slice()
              .sort((a, b) => a.effective_from.localeCompare(b.effective_from))
              .map((period) => (
                <li key={period.id} className="flex items-center gap-2 text-text">
                  <Badge tone="neutral">
                    <TaxCodeBadge value={regimeLabel(period.regime_code)} />
                  </Badge>
                  {t("account.regimeSection.effectiveFrom")}: {formatDate(period.effective_from)}
                </li>
              ))}
          </ul>
        )}
      </div>

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text">{t("account.tab.lossPocketTitle")}</h3>
          <LinkButton to="/investments/tax" variant="ghost" size="sm">
            {t("account.tab.seeFull")}
          </LinkButton>
        </div>
        <p className="mt-2 text-sm text-text-muted">{t("account.tab.lossPocketTotal")}</p>
        <p className="font-numeric text-lg font-semibold text-text">
          {accountTotal !== null ? formatMoney(accountTotal, "EUR") : "—"}
        </p>
      </div>
    </div>
  );
}
