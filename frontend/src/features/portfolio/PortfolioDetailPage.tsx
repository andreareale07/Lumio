import { PiggyBank } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { BackLink } from "../../components/ui/BackLink";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { formatMoney, formatPercent, formatQuantity, formatSignedMoney } from "../../lib/format";
import { PortfolioSummaryBlock } from "./PortfolioSummaryBlock";
import { usePortfolio, usePortfolioMarketDataAutoRefresh, usePortfolioPositions } from "./api";

/** Livello 1 del drill-down Investimenti: STESSO template di
 * `InvestmentsOverviewPage`/`PortfolioSummaryBlock`, scoped a un solo
 * Portfolio (o allo pseudo-scope "Asset senza portfolio" quando
 * `:portfolioId === "unassigned"`) — mai una pagina diversa/parallela,
 * cosi' i due livelli restano davvero lo stesso template nel tempo. Sotto
 * il blocco condiviso: solo l'elenco degli asset di questo ambito (il "cosa
 * ci sto vedendo dentro") — il libro mastro dei movimenti e' stato tolto
 * (richiesta esplicita dell'utente: la sezione asset basta da sola; per
 * registrare un nuovo movimento resta il bottone "Registra movimento" in
 * `InvestmentsOverviewPage`, che apre lo stesso `InvestmentTransactionFormDialog`
 * senza vincolarlo a un portfolio specifico). */
export function PortfolioDetailPage() {
  const { t } = useTranslation("portfolio");
  const { portfolioId: rawId } = useParams<{ portfolioId: string }>();
  const location = useLocation();
  const isUnassigned = rawId === "unassigned";
  const portfolioId = isUnassigned ? null : (rawId ?? null);
  const scope = isUnassigned ? { unassigned: true } : { portfolioId };

  usePortfolioMarketDataAutoRefresh();
  const portfolio = usePortfolio(isUnassigned ? null : portfolioId);
  const positions = usePortfolioPositions(scope);

  if (!isUnassigned && portfolio.isLoading) return <SkeletonRows rows={4} />;
  if (!isUnassigned && portfolio.isError) {
    return (
      <EmptyState
        icon={PiggyBank}
        title={t("detail.notFound.title")}
        description={t("detail.notFound.description")}
        action={
          <LinkButton to="/investments" size="sm">
            {t("detail.notFound.action")}
          </LinkButton>
        }
      />
    );
  }

  const title = isUnassigned ? t("detail.unassignedTitle") : portfolio.data?.name ?? "";
  // Il link "indietro" di AssetDetailPage usa questo per tornare qui invece
  // che sempre alla Panoramica generale — un asset puo' essere raggiunto da
  // piu' ambiti diversi, quindi si passa via `state` di navigazione (non
  // nell'URL: e' un dettaglio di provenienza, non un parametro della
  // risorsa) invece di un query param persistente.
  const backState = { from: location.pathname, label: title };

  const positionsList = positions.data?.positions ?? [];
  const positionsTotals =
    positionsList.length > 0
      ? {
          currency: positions.data!.currency,
          marketValue: positionsList.reduce((sum, p) => sum + Number(p.market_value), 0),
          costBasis: positionsList.reduce((sum, p) => sum + Number(p.cost_basis), 0),
          unrealizedPl: positionsList.reduce((sum, p) => sum + Number(p.unrealized_pl), 0),
        }
      : null;
  const positionsTotalsPct =
    positionsTotals && positionsTotals.costBasis !== 0 ? positionsTotals.unrealizedPl / positionsTotals.costBasis : null;

  // Passato come `belowCards` (non un fratello dopo `PortfolioSummaryBlock`):
  // l'utente ha chiesto l'elenco Asset subito sotto le card, prima della
  // Composizione — l'ordine e' deciso dal blocco condiviso, questa pagina
  // fornisce solo il contenuto dello slot.
  const assetsSection = (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4">
        <h3 className="text-sm font-semibold text-text">{t("detail.assets.title")}</h3>
        {positions.isLoading && <SkeletonRows rows={3} />}
        {positions.isError && (
          <ErrorState message={t("detail.assets.loadError")} onRetry={() => void positions.refetch()} />
        )}
        {positions.data && positions.data.positions.length === 0 && (
          <p className="text-sm text-text-muted">{t("detail.assets.empty")}</p>
        )}
        {positions.data && positions.data.positions.length > 0 && (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead className="text-left text-text-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">{t("detail.assets.table.asset")}</th>
                    <th className="px-3 py-2 font-medium">{t("detail.assets.table.account")}</th>
                    <th className="px-3 py-2 text-right font-medium">{t("detail.assets.table.quantity")}</th>
                    <th className="px-3 py-2 text-right font-medium">{t("detail.assets.table.currentValue")}</th>
                    <th className="px-3 py-2 text-right font-medium">{t("detail.assets.table.returnLabel")}</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.data.positions.map((p) => {
                    const unrealizedPl = Number(p.unrealized_pl);
                    const pct = Number(p.cost_basis) !== 0 ? unrealizedPl / Number(p.cost_basis) : null;
                    return (
                      <tr key={p.position_id} className="border-t border-border">
                        <td className="px-3 py-2 text-text">
                          <Link to={`/investments/assets/${p.asset_id}`} state={backState} className="hover:underline">
                            {p.asset_label}
                          </Link>
                        </td>
                        <td className="px-3 py-2 text-text-muted">{p.account_label}</td>
                        <td className="font-numeric px-3 py-2 text-right text-text-muted">{formatQuantity(p.quantity)}</td>
                        <td className="font-numeric px-3 py-2 text-right text-text">
                          {formatMoney(p.market_value, p.currency)}
                        </td>
                        <td
                          className={`font-numeric px-3 py-2 text-right ${unrealizedPl >= 0 ? "text-success" : "text-danger"}`}
                        >
                          {formatSignedMoney(unrealizedPl, p.currency)}
                          {pct !== null && ` (${formatPercent(pct, { signed: true })})`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                {positionsTotals && (
                  <tfoot>
                    <tr className="border-t-2 border-border font-bold">
                      <td className="px-3 py-2 text-text">{t("detail.assets.table.total")}</td>
                      <td className="px-3 py-2" />
                      <td className="px-3 py-2" />
                      <td className="font-numeric px-3 py-2 text-right text-text">
                        {formatMoney(positionsTotals.marketValue, positionsTotals.currency)}
                      </td>
                      <td
                        className={`font-numeric px-3 py-2 text-right ${positionsTotals.unrealizedPl >= 0 ? "text-success" : "text-danger"}`}
                      >
                        {formatSignedMoney(positionsTotals.unrealizedPl, positionsTotals.currency)}
                        {positionsTotalsPct !== null && ` (${formatPercent(positionsTotalsPct, { signed: true })})`}
                      </td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>

            <ul className="flex flex-col gap-2 md:hidden">
              {positions.data.positions.map((p) => {
                const unrealizedPl = Number(p.unrealized_pl);
                const pct = Number(p.cost_basis) !== 0 ? unrealizedPl / Number(p.cost_basis) : null;
                return (
                  <li key={p.position_id}>
                    <Link
                      to={`/investments/assets/${p.asset_id}`}
                      state={backState}
                      className="flex flex-col gap-1 rounded-xl border border-border p-3 text-sm hover:bg-surface-hover"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-text">{p.asset_label}</span>
                        <span className="font-numeric text-text">{formatMoney(p.market_value, p.currency)}</span>
                      </div>
                      <div className="flex items-center justify-between text-text-muted">
                        <span>{p.account_label}</span>
                        <span className={`font-numeric ${unrealizedPl >= 0 ? "text-success" : "text-danger"}`}>
                          {formatSignedMoney(unrealizedPl, p.currency)}
                          {pct !== null && ` (${formatPercent(pct, { signed: true })})`}
                        </span>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>

            {positionsTotals && (
              <div className="grid grid-cols-2 gap-3 border-t-2 border-border pt-3 text-sm font-bold md:hidden">
                <div>
                  <span className="block text-xs font-medium text-text-muted">{t("detail.assets.table.total")}</span>
                  {formatMoney(positionsTotals.marketValue, positionsTotals.currency)}
                </div>
                <div className={`text-right ${positionsTotals.unrealizedPl >= 0 ? "text-success" : "text-danger"}`}>
                  <span className="block text-xs font-medium text-text-muted">{t("detail.assets.table.returnLabel")}</span>
                  {formatSignedMoney(positionsTotals.unrealizedPl, positionsTotals.currency)}
                  {positionsTotalsPct !== null && ` (${formatPercent(positionsTotalsPct, { signed: true })})`}
                </div>
              </div>
            )}
          </>
        )}
      </div>
  );

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div>
        <BackLink to="/investments" label={t("detail.backLabel")} />
        <h1 className="mt-1 text-lg font-semibold text-text">{title}</h1>
        {isUnassigned && <p className="text-sm text-text-muted">{t("detail.unassignedDescription")}</p>}
        {!isUnassigned && portfolio.data?.description && (
          <p className="text-sm text-text-muted">{portfolio.data.description}</p>
        )}
      </div>

      <PortfolioSummaryBlock scope={scope} belowCards={assetsSection} />
    </div>
  );
}
