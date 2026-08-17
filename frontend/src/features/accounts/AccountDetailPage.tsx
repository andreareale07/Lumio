import { useState } from "react";
import { Landmark, Wallet } from "lucide-react";
import { useParams, useSearchParams } from "react-router-dom";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { BarComparisonChart } from "../../components/charts/BarComparisonChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DonutChart } from "../../components/charts/DonutChart";
import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { Skeleton, SkeletonRows } from "../../components/ui/Skeleton";
import { Tabs } from "../../components/ui/Tabs";
import { formatDate, formatMoney, formatPeriodLabel, formatSignedMoney } from "../../lib/format";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import {
  useAnalyticsBalanceHistory,
  useAnalyticsBalances,
  useAnalyticsByCategory,
  useAnalyticsCashFlow,
} from "../analytics/api";
import { formatBucketLabel } from "../analytics/chartData";
import { useTransactions } from "../transactions/api";
import { useAccounts } from "./api";
import { ACCOUNT_TYPE_LABELS } from "./labels";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "transactions", label: "Movimenti" },
  { key: "analytics", label: "Analytics" },
];

export function AccountDetailPage() {
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
    return <ErrorState message="Non siamo riusciti a caricare il conto." onRetry={() => void refetch()} />;
  }
  if (!account || !accountId) {
    return (
      <EmptyState
        icon={Landmark}
        title="Conto non trovato"
        description="Il conto richiesto non esiste o non è più disponibile."
        action={<LinkButton to="/accounts" size="sm">Torna ai conti</LinkButton>}
      />
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-text">{account.name}</h1>
          <p className="text-sm text-text-muted">
            {ACCOUNT_TYPE_LABELS[account.account_type]} · {account.currency}
          </p>
        </div>
        {accountBalance && (
          <span className="font-numeric text-2xl font-semibold text-text">
            {formatMoney(accountBalance.balance, account.currency)}
          </span>
        )}
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" && <AccountOverviewTab accountId={accountId} onSeeAll={() => setTab("transactions")} />}
      {tab === "transactions" && <AccountTransactionsTab accountId={accountId} />}
      {tab === "analytics" && <AccountAnalyticsTab accountId={accountId} currency={account.currency} />}
    </div>
  );
}

function AccountOverviewTab({ accountId, onSeeAll }: { accountId: string; onSeeAll: () => void }) {
  const recent = useTransactions({ financial_account_id: accountId, limit: 5 });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text">Ultimi movimenti</h3>
        <button type="button" onClick={onSeeAll} className="text-sm font-medium text-primary hover:underline">
          Vedi tutti
        </button>
      </div>
      {recent.isLoading && <SkeletonRows rows={4} />}
      {recent.isError && (
        <ErrorState message="Movimenti non disponibili." onRetry={() => void recent.refetch()} />
      )}
      {recent.data && recent.data.length === 0 && (
        <EmptyState
          icon={Wallet}
          title="Nessun movimento"
          description="I movimenti di questo conto appariranno qui."
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
      {isError && <ErrorState message="Movimenti non disponibili." onRetry={() => void refetch()} />}
      {transactions && transactions.length === 0 && (
        <EmptyState
          icon={Wallet}
          title="Nessun movimento"
          description="I movimenti importati o creati manualmente appariranno qui."
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
              Precedenti
            </button>
            <button
              type="button"
              disabled={transactions.length < PAGE_SIZE}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="text-sm text-text-muted disabled:opacity-40"
            >
              Successivi
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function AccountAnalyticsTab({ accountId, currency }: { accountId: string; currency: string }) {
  const { granularity: navGranularity, currentPeriod, trendWindow } = usePeriodNavigator({
    granularities: ["month", "quarter", "year"],
  });
  const period = { date_from: currentPeriod.date_from, date_to: currentPeriod.date_to, financial_account_id: accountId };
  const trendPeriod = { ...trendWindow, financial_account_id: accountId };

  const history = useAnalyticsBalanceHistory({ ...trendPeriod, granularity: navGranularity });
  const cashFlow = useAnalyticsCashFlow({ ...trendPeriod, granularity: navGranularity });
  const byCategory = useAnalyticsByCategory({ ...period, direction: "expense" });

  const historyGranularity = history.data?.granularity ?? "month";
  const trendPoints = (history.data?.points ?? []).map((p) => ({
    period: p.period,
    label: formatBucketLabel(p.period, historyGranularity),
    value: Number(p.balance),
  }));

  const cashFlowGranularity = cashFlow.data?.granularity ?? "month";
  const cashFlowBars = (cashFlow.data?.points ?? []).map((p) => ({
    period: p.period,
    label: formatBucketLabel(p.period, cashFlowGranularity),
    income: Number(p.income),
    expenses: Number(p.expenses),
  }));

  return (
    <div className="flex flex-col gap-4">
      <PeriodNavigator granularities={["month", "quarter", "year"]} />

      {history.isLoading && <Skeleton className="h-64 w-full" />}
      {history.data && (
        <ChartCard
          title="Saldo nel tempo"
          subtitle={formatPeriodLabel(history.data.period.date_from, history.data.period.date_to)}
          empty={trendPoints.length === 0}
          emptyState={<EmptyState icon={Landmark} title="Nessun dato" description="Lo storico apparirà con i primi movimenti." />}
          tableCaption="Saldo del conto nel tempo"
          tableHeaders={["Periodo", "Saldo"]}
          tableRows={trendPoints.map((p) => [p.label, formatMoney(p.value, currency)])}
        >
          <AreaTrendChart data={trendPoints} currency={currency} valueLabel="Saldo" />
        </ChartCard>
      )}

      {cashFlow.isLoading && <Skeleton className="h-64 w-full" />}
      {cashFlow.data && (
        <ChartCard
          title="Entrate vs Uscite"
          empty={cashFlowBars.every((p) => p.income === 0 && p.expenses === 0)}
          emptyState={<EmptyState icon={Wallet} title="Nessun movimento" description="Nessuna entrata o uscita in questo periodo." />}
          tableCaption="Entrate e uscite per mese"
          tableHeaders={["Periodo", "Entrate", "Uscite"]}
          tableRows={cashFlow.data.points.map((p) => [
            formatBucketLabel(p.period, cashFlowGranularity),
            formatMoney(p.income, currency),
            formatMoney(p.expenses, currency),
          ])}
        >
          <BarComparisonChart data={cashFlowBars} currency={currency} />
        </ChartCard>
      )}

      {byCategory.isLoading && <Skeleton className="h-64 w-full" />}
      {byCategory.data && (
        <ChartCard
          title="Spese per categoria"
          empty={byCategory.data.items.length === 0}
          emptyState={<EmptyState icon={Landmark} title="Nessuna spesa" description="Nessuna spesa classificata in questo periodo." />}
          tableCaption="Spese per categoria"
          tableHeaders={["Categoria", "Totale"]}
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
