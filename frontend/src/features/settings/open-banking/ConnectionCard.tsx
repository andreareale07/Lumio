import { AlertTriangle, ChevronDown, Landmark, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Button } from "../../../components/ui/Button";
import { formatDate, formatDateTime } from "../../../lib/format";
import type { BankConnection, BankConnectionAccount } from "../../../types/api";
import { needsRenewal, statusKeyOf } from "./bankStatus";
import { ConnectionStatusLine } from "./ConnectionStatusLine";
import type { SyncOutcome } from "./ConnectionStatusLine";

export type { SyncOutcome };

interface Props {
  connection: BankConnection;
  expanded: boolean;
  onToggle: () => void;
  syncing: boolean;
  outcome: SyncOutcome | null;
  accountPending: string | null;
  onSync: () => void;
  onRenew: () => void;
  onDisconnect: () => void;
  onImportAccount: (account: BankConnectionAccount) => void;
  onToggleAccount: (account: BankConnectionAccount, enabled: boolean) => void;
  onAccountDetails: (account: BankConnectionAccount) => void;
}

function AccountRow({
  account,
  pending,
  onImport,
  onToggle,
  onDetails,
}: {
  account: BankConnectionAccount;
  pending: boolean;
  onImport: () => void;
  onToggle: (enabled: boolean) => void;
  onDetails: () => void;
}) {
  const { t } = useTranslation("settings");
  const mapped = account.financial_account_id !== null;
  const title = account.name ?? account.product ?? t("items.bankConnections.page.connection.unnamedAccount");

  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="truncate font-medium text-text">{title}</p>
        <p className="text-sm text-text-muted">
          {[account.iban_masked, account.currency].filter(Boolean).join(" · ")}
        </p>
        {mapped && (
          <p className="text-sm text-text-muted">
            {t("items.bankConnections.page.connection.imported", { count: account.transactions_imported })}
          </p>
        )}
        {mapped && (
          <button
            type="button"
            onClick={onDetails}
            className="inline-flex min-h-11 items-center gap-1.5 text-sm font-medium text-primary hover:underline md:min-h-0"
          >
            {(account.balance_snapshot?.continuity_gaps ?? 0) > 0 && (
              <AlertTriangle className="h-4 w-4 text-danger" aria-hidden="true" />
            )}
            {t("items.bankConnections.page.connection.syncDetails")}
          </button>
        )}
      </div>
      {mapped ? (
        // Interruttore con testo esplicito: lo stato non si affida al solo colore e il bersaglio e' da 44px.
        <button
          type="button"
          role="switch"
          aria-checked={account.enabled}
          disabled={pending}
          onClick={() => onToggle(!account.enabled)}
          className="flex min-h-11 items-center gap-3 self-start rounded-lg px-1 text-sm text-text disabled:opacity-50 sm:self-auto"
        >
          <span
            aria-hidden="true"
            className={`relative inline-block h-6 w-11 shrink-0 rounded-full transition-colors ${
              account.enabled ? "bg-primary" : "bg-border"
            }`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${
                account.enabled ? "left-[1.375rem]" : "left-0.5"
              }`}
            />
          </span>
          {account.enabled
            ? t("items.bankConnections.page.connection.importOn")
            : t("items.bankConnections.page.connection.importOff")}
        </button>
      ) : (
        <Button variant="secondary" size="sm" onClick={onImport} className="w-full sm:w-auto">
          {t("items.bankConnections.page.connection.importAccount")}
        </Button>
      )}
    </li>
  );
}

export function ConnectionCard({
  connection,
  expanded,
  onToggle,
  syncing,
  outcome,
  accountPending,
  onSync,
  onRenew,
  onDisconnect,
  onImportAccount,
  onToggleAccount,
  onAccountDetails,
}: Props) {
  const { t } = useTranslation("settings");
  const statusKey = statusKeyOf(connection);
  const renewal = needsRenewal(connection);
  const canSync = connection.status === "active" && connection.accounts.some((a) => a.enabled);
  const hasUnmapped = connection.accounts.some((a) => a.financial_account_id === null);
  const lastErrorText = connection.last_error
    ? (t(`items.bankConnections.page.lastErrors.${connection.last_error}`, { defaultValue: "" }) as string) ||
      t("items.bankConnections.page.lastErrors.generic")
    : null;

  return (
    <section aria-label={connection.aspsp_name}>
      <div className="flex flex-col gap-1 p-4 pb-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="-mx-2 flex min-h-11 items-center gap-3 rounded-lg px-2 text-left hover:bg-surface-hover"
        >
          <Landmark className="h-6 w-6 shrink-0 text-text-muted" aria-hidden="true" />
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium text-text">{connection.aspsp_name}</span>
            <span className="block truncate text-sm text-text-muted">
              {t("items.bankConnections.page.connection.accountsTitle", { count: connection.accounts.length })}
            </span>
          </span>
          <ChevronDown
            className={`h-5 w-5 shrink-0 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
        <ConnectionStatusLine
          connection={connection}
          syncing={syncing}
          outcome={outcome}
          canSync={canSync}
          onRenew={onRenew}
          onRetry={onSync}
        />
      </div>

      {expanded && (
        <div className="flex flex-col gap-3 px-4 pb-4">
      <div className="flex flex-col gap-0.5 text-sm text-text-muted">
        {connection.valid_until && connection.days_until_expiry !== null && connection.status === "active" && (
          <p>
            {t("items.bankConnections.page.connection.validUntil", {
              date: formatDate(connection.valid_until),
              count: Math.max(connection.days_until_expiry, 0),
            })}
          </p>
        )}
        <p>
          {t("items.bankConnections.page.connection.lastSync", {
            value: connection.last_sync_at
              ? formatDateTime(connection.last_sync_at)
              : t("items.bankConnections.page.connection.neverSynced"),
          })}
        </p>
      </div>

      {renewal && (
        <p className="text-sm text-text-muted">
          {statusKey === "expired"
            ? t("items.bankConnections.page.connection.expiredHint")
            : t("items.bankConnections.page.connection.expiringHint", {
                count: Math.max(connection.days_until_expiry ?? 0, 0),
              })}
        </p>
      )}

      {lastErrorText && !renewal && (
        <p className="text-sm text-danger">
          {lastErrorText}
        </p>
      )}

      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          {t("items.bankConnections.page.connection.accountsTitle", { count: connection.accounts.length })}
        </h4>
        {connection.accounts.length === 0 ? (
          <p className="py-2 text-sm text-text-muted">{t("items.bankConnections.page.connection.noAccounts")}</p>
        ) : (
          <ul className="divide-y divide-border">
            {connection.accounts.map((account) => (
              <AccountRow
                key={account.id}
                account={account}
                pending={accountPending === account.id}
                onImport={() => onImportAccount(account)}
                onToggle={(enabled) => onToggleAccount(account, enabled)}
                onDetails={() => onAccountDetails(account)}
              />
            ))}
          </ul>
        )}
        {hasUnmapped && (
          <p className="text-sm text-text-muted">{t("items.bankConnections.page.connection.chooseAccounts")}</p>
        )}
      </div>

      {!syncing && outcome && !outcome.error && outcome.imported > 0 && (
        <Link to="/transactions" className="inline-flex min-h-11 items-center text-sm font-medium text-primary hover:underline md:min-h-0">
          {t("items.bankConnections.page.connection.viewTransactions")}
        </Link>
      )}

      <div className="grid grid-cols-1 gap-2 sm:flex sm:flex-wrap sm:justify-end">
        <Button
          variant="ghost"
          onClick={onDisconnect}
          className="text-danger hover:bg-danger-bg sm:order-first sm:mr-auto"
        >
          {t("items.bankConnections.page.connection.disconnect")}
        </Button>
        {connection.status === "active" && (
          <Button onClick={onSync} disabled={!canSync || syncing} title={!canSync ? t("items.bankConnections.page.connection.syncDisabled") : undefined}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {t("items.bankConnections.page.connection.syncNow")}
          </Button>
        )}
      </div>
      {!canSync && connection.status === "active" && (
        <p className="text-sm text-text-muted">{t("items.bankConnections.page.connection.syncDisabled")}</p>
      )}
        </div>
      )}
    </section>
  );
}
