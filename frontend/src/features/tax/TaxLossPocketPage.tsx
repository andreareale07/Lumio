import { useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { PiggyBank, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../../lib/apiClient";
import { usePageToolbar } from "../../components/layout/PageToolbarContext";
import { BackLink } from "../../components/ui/BackLink";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { formatDate, formatMoney } from "../../lib/format";
import { useAccounts } from "../accounts/api";
import type { TaxRegimePeriod } from "../../types/api";
import { useTaxLossOpenings, useLossPocket } from "./api";
import { TaxLossOpeningDialog } from "./TaxLossOpeningDialog";

/** `/investments/tax` (SPEC_TAX_REGIME.md FETTA 1) — due sezioni implicite
 * (amministrato per conto + dichiarativo aggregato), MAI un totale
 * cross-perimetro: amministrato e dichiarativo sono due contenitori
 * separati per legge, sommarli sarebbe un numero senza significato. */
export function TaxLossPocketPage() {
  const { t } = useTranslation("tax");
  const today = new Date().toISOString().slice(0, 10);
  // Nessun filtro per account_type: un conto "checking" puo' comunque
  // essere un conto titoli in pratica (vedi AccountEditPage) — un regime
  // impostato su QUALUNQUE conto conta per lo stato "hasAnyRegime" sotto.
  const { data: accounts } = useAccounts();

  const regimeQueries = useQueries({
    queries: (accounts ?? []).map((a) => ({
      queryKey: ["tax", "accounts", a.id, "regimes"],
      queryFn: () => api.get<TaxRegimePeriod[]>(`/tax/accounts/${a.id}/regimes`),
      enabled: !!accounts,
    })),
  });
  const regimesLoaded = accounts !== undefined && regimeQueries.every((q) => q.data !== undefined);
  const hasAnyRegime = regimeQueries.some((q) => (q.data?.length ?? 0) > 0);

  const openings = useTaxLossOpenings();
  const pocket = useLossPocket(today);
  const [openingDialogOpen, setOpeningDialogOpen] = useState(false);

  const accountNameById = new Map((accounts ?? []).map((a) => [a.id, a.name]));

  const isLoading = !regimesLoaded || openings.isLoading || pocket.isLoading;
  const isError = openings.isError || pocket.isError;

  const newOpeningButton = (
    <Button size="sm" onClick={() => setOpeningDialogOpen(true)}>
      <Plus className="h-4 w-4" /> {t("lossPocket.page.newOpening")}
    </Button>
  );
  const toolbarPortal = usePageToolbar(hasAnyRegime ? newOpeningButton : null);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      {toolbarPortal}
      <div>
        <BackLink to="/investments" label={t("portfolio:overview.title")} />
        <h1 className="mt-1 text-lg font-semibold text-text">{t("lossPocket.page.title")}</h1>
        <p className="text-sm text-text-muted">{t("lossPocket.page.intro")}</p>
      </div>
      {hasAnyRegime && <div className="md:hidden">{newOpeningButton}</div>}

      <p className="rounded-lg bg-warning-bg px-3 py-2 text-xs text-warning">{t("common.disclaimer")}</p>

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState onRetry={() => void pocket.refetch()} />}

      {!isLoading && !isError && !hasAnyRegime && (
        <EmptyState
          icon={PiggyBank}
          title={t("lossPocket.emptyStates.noRegime.title")}
          description={t("lossPocket.emptyStates.noRegime.description")}
          action={<LinkButton to="/accounts">{t("lossPocket.emptyStates.noRegime.action")}</LinkButton>}
        />
      )}

      {!isLoading && !isError && hasAnyRegime && (openings.data?.length ?? 0) === 0 && (
        <EmptyState
          icon={PiggyBank}
          title={t("lossPocket.emptyStates.noData.title")}
          description={t("lossPocket.emptyStates.noData.description")}
          action={<Button onClick={() => setOpeningDialogOpen(true)}>{t("lossPocket.emptyStates.noData.action")}</Button>}
        />
      )}

      {!isLoading && !isError && hasAnyRegime && (openings.data?.length ?? 0) > 0 && pocket.data && (
        <div className="flex flex-col gap-3">
          {Object.entries(
            groupRowsByPerimeter(pocket.data.rows, pocket.data.totals_by_perimeter),
          ).map(([perimeter, group]) => (
            <Card key={perimeter} className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-text">
                  {perimeter === "dichiarativo"
                    ? t("lossPocket.page.perimeterAggregate")
                    : accountNameById.get(perimeter) ?? perimeter}
                </h3>
                <div className="text-right">
                  <p className="text-xs text-text-muted">
                    {t("lossPocket.page.atLeastPrefix")} · {t("lossPocket.page.capacityLabel")}
                  </p>
                  <p className="font-numeric text-lg font-semibold text-text">
                    {formatMoney(group.total, currencyGuess())}
                  </p>
                  {group.total === 0 && (
                    <p className="text-xs text-text-muted">{t("lossPocket.page.capacityExhausted")}</p>
                  )}
                </div>
              </div>

              <div className="hidden overflow-x-auto md:block">
                <table className="w-full text-sm">
                  <thead className="text-left text-text-muted">
                    <tr>
                      <th className="px-2 py-1.5 font-medium">{t("lossPocket.table.formationDate")}</th>
                      <th className="px-2 py-1.5 text-right font-medium">{t("lossPocket.table.nominal")}</th>
                      <th className="px-2 py-1.5 text-right font-medium">{t("lossPocket.table.coefficient")}</th>
                      <th className="px-2 py-1.5 text-right font-medium">{t("lossPocket.table.usable")}</th>
                      <th className="px-2 py-1.5 font-medium">{t("lossPocket.table.expiresOn")}</th>
                      <th className="px-2 py-1.5 font-medium">{t("lossPocket.table.source")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.rows.map((row, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="px-2 py-1.5 text-text">{formatDate(row.formation_date)}</td>
                        <td className="font-numeric px-2 py-1.5 text-right text-text-muted">
                          {formatMoney(row.nominal, "EUR")}
                        </td>
                        <td className="font-numeric px-2 py-1.5 text-right text-text-muted">
                          {(Number(row.coefficient) * 100).toFixed(2)}%
                        </td>
                        <td className="font-numeric px-2 py-1.5 text-right text-text">
                          {formatMoney(row.usable_amount, "EUR")}
                        </td>
                        <td className="px-2 py-1.5">
                          <span className={row.is_expired ? "text-danger" : "text-text-muted"}>
                            {formatDate(row.expires_on)}
                            {row.is_expired && ` · ${t("lossPocket.table.expired")}`}
                          </span>
                        </td>
                        <td className="px-2 py-1.5">
                          <Badge tone="neutral">{t("lossPocket.table.sourceUserOpening")}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <ul className="flex flex-col gap-2 md:hidden">
                {group.rows.map((row, i) => (
                  <li key={i} className="rounded-lg border border-border p-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-text">{formatDate(row.formation_date)}</span>
                      <span className="font-numeric text-text">{formatMoney(row.usable_amount, "EUR")}</span>
                    </div>
                    <p className="text-text-muted">
                      {t("lossPocket.table.nominal")}: {formatMoney(row.nominal, "EUR")} ·{" "}
                      {t("lossPocket.table.coefficient")}: {(Number(row.coefficient) * 100).toFixed(2)}%
                    </p>
                    <p className={row.is_expired ? "text-danger" : "text-text-muted"}>
                      {t("lossPocket.table.expiresOn")}: {formatDate(row.expires_on)}
                      {row.is_expired && ` · ${t("lossPocket.table.expired")}`}
                    </p>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}

      <TaxLossOpeningDialog open={openingDialogOpen} onClose={() => setOpeningDialogOpen(false)} />
    </div>
  );
}

function currencyGuess() {
  // FETTA 1: i saldi di apertura non hanno un campo valuta esplicito (il
  // nominale e' sempre nella valuta legale del regime, EUR per l'Italia) —
  // nessuna conversione qui, coerente con "il nominale non viene mai
  // mutato dal calcolo" del motore.
  return "EUR";
}

function groupRowsByPerimeter(
  rows: { formation_date: string; nominal: string; coefficient: string; usable_amount: string; expires_on: string; is_expired: boolean; perimeter: string }[],
  totals: Record<string, string>,
) {
  const groups: Record<string, { rows: typeof rows; total: number }> = {};
  for (const row of rows) {
    if (!groups[row.perimeter]) groups[row.perimeter] = { rows: [], total: Number(totals[row.perimeter] ?? 0) };
    groups[row.perimeter].rows.push(row);
  }
  // Perimetri con solo righe scadute non compaiono in `totals` (nessuna
  // riga non scaduta) ma devono restare visibili con "0,00 €" — mai
  // collassare nell'empty state (SPEC_TAX_REGIME.md, stato 3).
  for (const perimeter of Object.keys(totals)) {
    if (!groups[perimeter]) groups[perimeter] = { rows: [], total: Number(totals[perimeter]) };
  }
  return groups;
}
