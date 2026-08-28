import { useState } from "react";
import { Landmark, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { usePageToolbar } from "../../components/layout/PageToolbarContext";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatMoney } from "../../lib/format";
import { useAnalyticsBalances } from "../analytics/api";
import { AccountDeleteDialog } from "./AccountDeleteDialog";
import { AccountFormDialog } from "./AccountFormDialog";
import { useAccounts, useSetAccountActive } from "./api";
import { useAccountTypeLabel } from "./labels";
import type { FinancialAccount } from "../../types/api";

export function AccountsPage() {
  const { t } = useTranslation("accounts");
  const accountTypeLabel = useAccountTypeLabel();
  const { data: accounts, isLoading, isError, refetch } = useAccounts();
  const setActive = useSetAccountActive();
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FinancialAccount | null>(null);
  // Saldo derivato (SPEC §18: nessun campo `balance` sul modello) — vedi
  // `app/services/analytics.py::account_balances`.
  const balances = useAnalyticsBalances();

  const addAccountButton = (
    <Button size="sm" onClick={() => setCreateOpen(true)}>
      <Plus className="h-4 w-4" /> {t("page.addAccount")}
    </Button>
  );
  const toolbarPortal = usePageToolbar(addAccountButton);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      {toolbarPortal}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text">{t("page.title")}</h1>
        <div className="md:hidden">{addAccountButton}</div>
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
          action={<Button onClick={() => setCreateOpen(true)}>{t("page.addAccount")}</Button>}
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
                    <Link
                      to={`/accounts/${account.id}/edit`}
                      className="text-sm text-text-muted hover:text-text"
                    >
                      {t("page.edit")}
                    </Link>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setActive.mutate({ id: account.id, isActive: !account.is_active })}
                      className="text-sm text-text-muted hover:text-text"
                    >
                      {account.is_active ? t("page.archive") : t("page.unarchive")}
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(account)}
                      className="text-sm text-danger hover:underline"
                    >
                      {t("page.delete")}
                    </button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <AccountFormDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <AccountDeleteDialog account={deleteTarget} onClose={() => setDeleteTarget(null)} />
    </div>
  );
}
