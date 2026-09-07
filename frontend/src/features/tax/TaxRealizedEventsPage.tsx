import { useState } from "react";
import { ChevronLeft, ChevronRight, Receipt } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { PAGE_WIDTH_WIDE } from "../../components/layout/pageWidths";
import { BackLink } from "../../components/ui/BackLink";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Select } from "../../components/ui/Select";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { formatDate, formatMoney } from "../../lib/format";
import { useAccounts } from "../accounts/api";
import { useAssets } from "../portfolio/api";
import type { ClassifiedRealizedEvent } from "../../types/api";
import { useRealizedEvents } from "./api";
import { AssetCell } from "./components";
import { TaxEventOverrideDialog } from "./TaxEventOverrideDialog";

const PAGE_SIZE = 25;

/** `/investments/tax/realized-events` — elenco completo, paginato/filtrabile,
 * degli eventi realizzati (FETTA 2). Estratto da una sezione inline in
 * `TaxLossPocketPage` (segnalazione dell'utente: una lista che cresce senza
 * limite col tempo non può stare tutta in una pagina non paginata) — stesso
 * impianto di `TransactionsPage.tsx` (filtri via URL, tabella desktop + card
 * mobile, Prev/Next), ma con un conteggio esatto (`total` dal backend) invece
 * dell'euristica "pagina piena = forse ce n'è un'altra", perché qui il
 * calcolo è già tutto in memoria lato server. */
export function TaxRealizedEventsPage() {
  const { t } = useTranslation("tax");
  const today = new Date().toISOString().slice(0, 10);
  const [searchParams, setSearchParams] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const [overrideEvent, setOverrideEvent] = useState<ClassifiedRealizedEvent | null>(null);

  const assetId = searchParams.get("asset") ?? "";
  const accountId = searchParams.get("account") ?? "";
  const excludedOnly = searchParams.get("excluded") === "1";

  const { data: assets } = useAssets();
  const { data: accounts } = useAccounts();
  const assetById = new Map((assets ?? []).map((a) => [a.id, a]));
  const accountNameById = new Map((accounts ?? []).map((a) => [a.id, a.name]));

  const {
    data: page,
    isLoading,
    isError,
    refetch,
  } = useRealizedEvents({
    on: today,
    asset_id: assetId || undefined,
    financial_account_id: accountId || undefined,
    excluded_only: excludedOnly || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const updateFilter = (key: string, value: string) => {
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  const events = page?.items ?? [];
  const total = page?.total ?? 0;

  return (
    <div className={PAGE_WIDTH_WIDE}>
      <div>
        <BackLink to="/investments/tax" label={t("lossPocket.page.title")} />
        <h1 className="mt-1 text-lg font-semibold text-text">{t("realizedEventsPage.title")}</h1>
        <p className="text-sm text-text-muted">{t("realizedEventsPage.intro")}</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select
          aria-label={t("realizedEventsPage.filters.asset")}
          value={assetId}
          onChange={(e) => updateFilter("asset", e.target.value)}
          className="w-auto"
        >
          <option value="">{t("realizedEventsPage.filters.allAssets")}</option>
          {(assets ?? []).map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.symbol ?? asset.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label={t("realizedEventsPage.filters.account")}
          value={accountId}
          onChange={(e) => updateFilter("account", e.target.value)}
          className="w-auto"
        >
          <option value="">{t("realizedEventsPage.filters.allAccounts")}</option>
          {(accounts ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>
        <button
          type="button"
          onClick={() => updateFilter("excluded", excludedOnly ? "" : "1")}
          aria-pressed={excludedOnly}
          className={`inline-flex h-10 items-center rounded-lg border px-3 text-sm font-medium ${
            excludedOnly ? "border-primary bg-primary/10 text-primary" : "border-border text-text-muted"
          }`}
        >
          {t("realizedEventsPage.filters.excludedOnly")}
        </button>
      </div>

      {isLoading && <SkeletonRows rows={6} />}
      {isError && <ErrorState onRetry={() => void refetch()} />}

      {!isLoading && !isError && events.length === 0 && (
        <EmptyState
          icon={Receipt}
          title={t("realizedEventsPage.empty.title")}
          description={t("realizedEventsPage.empty.description")}
        />
      )}

      {!isLoading && !isError && events.length > 0 && (
        <>
          <div className="hidden overflow-hidden rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead className="bg-surface-hover text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("realizedEventsPage.table.date")}</th>
                  <th className="px-3 py-2 font-medium">{t("realizedEventsPage.table.asset")}</th>
                  <th className="px-3 py-2 font-medium">{t("realizedEventsPage.table.account")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("realizedEventsPage.table.amount")}</th>
                  <th className="px-3 py-2 font-medium">{t("realizedEventsPage.table.status")}</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {events.map((event, i) => (
                  <tr key={i} className="border-t border-border">
                    <td className="px-3 py-2 text-text-muted">{formatDate(event.trade_date)}</td>
                    <td className="px-3 py-2">
                      <AssetCell assetId={event.asset_id} assetById={assetById} />
                    </td>
                    <td className="px-3 py-2 text-text-muted">
                      {accountNameById.get(event.financial_account_id) ?? event.financial_account_id}
                    </td>
                    <td
                      className={`font-numeric px-3 py-2 text-right ${
                        Number(event.gain_or_loss) >= 0 ? "text-success" : "text-danger"
                      }`}
                    >
                      {formatMoney(event.gain_or_loss, "EUR")}
                    </td>
                    <td className="px-3 py-2 text-xs text-text-muted">
                      {event.excluded_reason &&
                        t(`lossPocket.excludedReason.${event.excluded_reason}`, {
                          defaultValue: event.excluded_reason,
                        })}
                      {event.is_overridden && ` · ${t("eventOverride.overriddenBadge")}`}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button variant="ghost" size="sm" onClick={() => setOverrideEvent(event)}>
                        {t("eventOverride.correct")}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-2 md:hidden">
            {events.map((event, i) => (
              <button
                key={i}
                onClick={() => setOverrideEvent(event)}
                className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-3 text-left"
              >
                <div className="flex items-center justify-between">
                  <AssetCell assetId={event.asset_id} assetById={assetById} />
                  <span
                    className={`font-numeric ${Number(event.gain_or_loss) >= 0 ? "text-success" : "text-danger"}`}
                  >
                    {formatMoney(event.gain_or_loss, "EUR")}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm text-text-muted">
                  <span>
                    {event.excluded_reason &&
                      t(`lossPocket.excludedReason.${event.excluded_reason}`, {
                        defaultValue: event.excluded_reason,
                      })}
                    {event.is_overridden && ` · ${t("eventOverride.overriddenBadge")}`}
                  </span>
                  <span>{formatDate(event.trade_date)}</span>
                </div>
              </button>
            ))}
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-text-muted">
              {t("realizedEventsPage.pagination.showing", {
                from: total === 0 ? 0 : offset + 1,
                to: Math.min(offset + PAGE_SIZE, total),
                total,
              })}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="link"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                <ChevronLeft className="h-4 w-4" /> {t("realizedEventsPage.pagination.previous")}
              </Button>
              <Button
                variant="link"
                size="sm"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                {t("realizedEventsPage.pagination.next")} <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}

      <TaxEventOverrideDialog event={overrideEvent} onClose={() => setOverrideEvent(null)} />
    </div>
  );
}
