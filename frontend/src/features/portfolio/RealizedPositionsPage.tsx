import { useState } from "react";
import { ChevronLeft, ChevronRight, TrendingUp } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { PAGE_WIDTH_WIDE } from "../../components/layout/pageWidths";
import { BackLink } from "../../components/ui/BackLink";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Select } from "../../components/ui/Select";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { formatQuantity, formatSignedMoney } from "../../lib/format";
import { useAccounts } from "../accounts/api";
import { AssetPicker } from "./AssetPicker";
import { usePortfolio, useRealizedPositions } from "./api";

const PAGE_SIZE = 25;

/** `/investments/realized-pl` — elenco completo, paginato/filtrabile, di
 * OGNI posizione con un P&L realizzato non nullo (aperta o chiusa che sia
 * — mai solo "posizioni chiuse": una posizione ancora aperta può avere un
 * residuo di realizzato da vendite parziali passate, la somma della lista
 * deve sempre coincidere col numero mostrato sulla card "Utile realizzato").
 * Scope via query string (`?portfolio=<id>`, `?portfolio=unassigned`,
 * assente = tutto il workspace) — stesso `?portfolio=unassigned` di
 * `PortfolioDetailPage`, stesso impianto di `TaxRealizedEventsPage.tsx`. */
export function RealizedPositionsPage() {
  const { t } = useTranslation("portfolio");
  const [searchParams, setSearchParams] = useSearchParams();
  const [offset, setOffset] = useState(0);

  const portfolioParam = searchParams.get("portfolio");
  const isUnassigned = portfolioParam === "unassigned";
  const portfolioId = isUnassigned ? null : (portfolioParam ?? null);
  const scope = isUnassigned ? { unassigned: true } : { portfolioId };

  const assetId = searchParams.get("asset") ?? "";
  const accountId = searchParams.get("account") ?? "";

  const { data: accounts } = useAccounts();
  const portfolio = usePortfolio(portfolioId);

  const {
    data: page,
    isLoading,
    isError,
    refetch,
  } = useRealizedPositions({
    ...scope,
    assetId: assetId || undefined,
    accountId: accountId || undefined,
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

  const positions = page?.positions ?? [];
  const total = page?.total ?? 0;

  const backTo = portfolioParam ? `/investments/portfolios/${portfolioParam}` : "/investments";
  const backLabel = isUnassigned
    ? t("detail.unassignedTitle")
    : portfolioParam
      ? (portfolio.data?.name ?? t("overview.title"))
      : t("overview.title");

  return (
    <div className={PAGE_WIDTH_WIDE}>
      <div>
        <BackLink to={backTo} label={backLabel} />
        <h1 className="mt-1 text-lg font-semibold text-text">{t("summaryBlock.kpi.realizedPl")}</h1>
        <p className="text-sm text-text-muted">{t("realizedPositionsPage.intro")}</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="w-56">
          <AssetPicker
            label={t("realizedPositionsPage.filters.asset")}
            value={assetId}
            includeEmptyOption
            onChange={(e) => updateFilter("asset", e.target.value)}
          />
        </div>
        <Select
          aria-label={t("realizedPositionsPage.filters.account")}
          value={accountId}
          onChange={(e) => updateFilter("account", e.target.value)}
          className="w-auto"
        >
          <option value="">{t("realizedPositionsPage.filters.allAccounts")}</option>
          {(accounts ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>
      </div>

      {isLoading && <SkeletonRows rows={6} />}
      {isError && <ErrorState onRetry={() => void refetch()} />}

      {!isLoading && !isError && positions.length === 0 && (
        <EmptyState
          icon={TrendingUp}
          title={t("realizedPositionsPage.empty.title")}
          description={t("realizedPositionsPage.empty.description")}
        />
      )}

      {!isLoading && !isError && positions.length > 0 && (
        <>
          <div className="hidden overflow-hidden rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead className="bg-surface-hover text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("realizedPositionsPage.table.asset")}</th>
                  <th className="px-3 py-2 font-medium">{t("realizedPositionsPage.table.account")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("realizedPositionsPage.table.quantity")}</th>
                  <th className="px-3 py-2 font-medium">{t("realizedPositionsPage.table.status")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("realizedPositionsPage.table.realizedPl")}</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => (
                  <tr key={position.position_id} className="border-t border-border">
                    <td className="px-3 py-2">
                      <Link
                        to={`/investments/assets/${position.asset_id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {position.asset_label}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-text-muted">{position.account_label}</td>
                    <td className="font-numeric px-3 py-2 text-right text-text-muted">{formatQuantity(position.quantity)}</td>
                    <td className="px-3 py-2">
                      {Number(position.quantity) === 0 ? (
                        <Badge tone="neutral">{t("realizedPositionsPage.status.closed")}</Badge>
                      ) : (
                        <Badge tone="success">{t("realizedPositionsPage.status.open")}</Badge>
                      )}
                    </td>
                    <td
                      className={`font-numeric px-3 py-2 text-right ${
                        Number(position.realized_pl) >= 0 ? "text-success" : "text-danger"
                      }`}
                    >
                      {formatSignedMoney(position.realized_pl, position.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-2 md:hidden">
            {positions.map((position) => (
              <Link
                key={position.position_id}
                to={`/investments/assets/${position.asset_id}`}
                className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-primary">{position.asset_label}</span>
                  <span
                    className={`font-numeric ${Number(position.realized_pl) >= 0 ? "text-success" : "text-danger"}`}
                  >
                    {formatSignedMoney(position.realized_pl, position.currency)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm text-text-muted">
                  <span>{position.account_label}</span>
                  {Number(position.quantity) === 0 ? (
                    <Badge tone="neutral">{t("realizedPositionsPage.status.closed")}</Badge>
                  ) : (
                    <Badge tone="success">{t("realizedPositionsPage.status.open")}</Badge>
                  )}
                </div>
              </Link>
            ))}
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-text-muted">
              {t("realizedPositionsPage.pagination.showing", {
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
                <ChevronLeft className="h-4 w-4" /> {t("realizedPositionsPage.pagination.previous")}
              </Button>
              <Button
                variant="link"
                size="sm"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                {t("realizedPositionsPage.pagination.next")} <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
