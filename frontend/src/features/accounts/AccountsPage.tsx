import { useState } from "react";
import { Landmark, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatMoney } from "../../lib/format";
import { useAnalyticsBalances } from "../analytics/api";
import type { FinancialAccount } from "../../types/api";
import { AccountFormDialog } from "./AccountFormDialog";
import { useAccounts, useSetAccountActive } from "./api";
import { useAccountTypeLabel } from "./labels";

export function AccountsPage() {
  const { t } = useTranslation("accounts");
  const accountTypeLabel = useAccountTypeLabel();
  const { data: accounts, isLoading, isError, refetch } = useAccounts();
  const setActive = useSetAccountActive();
  const [formAccount, setFormAccount] = useState<FinancialAccount | null | undefined>(undefined);
  // Saldo derivato (SPEC §18: nessun campo `balance` sul modello) — vedi
  // `app/services/analytics.py::account_balances`.
  const balances = useAnalyticsBalances();

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text">{t("page.title")}</h1>
        <Button size="sm" onClick={() => setFormAccount(null)}>
          <Plus className="h-4 w-4" /> {t("page.addAccount")}
        </Button>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      )}

      {isError && <ErrorState message={t("page.loadError")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && accounts && accounts.length === 0 && (
        <EmptyState
          icon={Landmark}
          title={t("page.empty.title")}
          description={t("page.empty.description")}
          action={<Button onClick={() => setFormAccount(null)}>{t("page.addAccount")}</Button>}
        />
      )}

      {!isLoading && !isError && accounts && accounts.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {accounts.map((account) => {
            const balance = balances.data?.accounts.find((a) => a.financial_account_id === account.id);
            return (
              <Card key={account.id} className="flex flex-col gap-2">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-semibold text-text">{account.name}</p>
                    <p className="text-sm text-text-muted">{accountTypeLabel(account.account_type)}</p>
                  </div>
                  {!account.is_active && <Badge tone="neutral">{t("page.archivedBadge")}</Badge>}
                </div>
                {balance ? (
                  <span className="font-numeric text-xl font-semibold text-text">
                    {formatMoney(balance.balance, account.currency)}
                  </span>
                ) : (
                  <Skeleton className="h-7 w-24" />
                )}
                <div className="mt-2 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Link to={`/accounts/${account.id}`} className="text-sm font-medium text-primary hover:underline">
                      {t("page.open")}
                    </Link>
                    <button
                      type="button"
                      onClick={() => setFormAccount(account)}
                      className="text-sm text-text-muted hover:text-text"
                    >
                      {t("page.edit")}
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActive.mutate({ id: account.id, isActive: !account.is_active })}
                    className="text-sm text-text-muted hover:text-text"
                  >
                    {account.is_active ? t("page.archive") : t("page.unarchive")}
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <AccountFormDialog
        open={formAccount !== undefined}
        onClose={() => setFormAccount(undefined)}
        account={formAccount}
      />
    </div>
  );
}
