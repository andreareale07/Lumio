import { useState } from "react";
import { PiggyBank, Plus, Trash2 } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";

import { BackLink } from "../../components/ui/BackLink";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { formatDate, formatMoney, formatPercent, formatSignedMoney } from "../../lib/format";
import { InvestmentTransactionFormDialog } from "./InvestmentTransactionFormDialog";
import { PortfolioSummaryBlock } from "./PortfolioSummaryBlock";
import { INVESTMENT_TRANSACTION_TYPE_LABELS } from "./labels";
import {
  useAssets,
  usePortfolio,
  usePortfolioPositions,
  useDeleteInvestmentTransaction,
  useInvestmentTransactions,
} from "./api";

const PAGE_SIZE = 25;

/** Livello 1 del drill-down Investimenti: STESSO template di
 * `InvestmentsOverviewPage`/`PortfolioSummaryBlock`, scoped a un solo
 * Portfolio (o allo pseudo-scope "Asset senza portfolio" quando
 * `:portfolioId === "unassigned"`) — mai una pagina diversa/parallela,
 * cosi' i due livelli restano davvero lo stesso template nel tempo. Sotto
 * il blocco condiviso: l'elenco degli asset di questo ambito (il "cosa ci
 * sto vedendo dentro") e il libro mastro dei movimenti, esattamente come
 * `PurchasesList` sta sotto le card in `AssetDetailPage`. */
export function PortfolioDetailPage() {
  const { portfolioId: rawId } = useParams<{ portfolioId: string }>();
  const location = useLocation();
  const isUnassigned = rawId === "unassigned";
  const portfolioId = isUnassigned ? null : (rawId ?? null);
  const scope = isUnassigned ? { unassigned: true } : { portfolioId };

  const portfolio = usePortfolio(isUnassigned ? null : portfolioId);
  const [offset, setOffset] = useState(0);
  const [txnDialogOpen, setTxnDialogOpen] = useState(false);
  const [toDelete, setToDelete] = useState<{ id: string } | null>(null);

  const positions = usePortfolioPositions(scope);
  const transactions = useInvestmentTransactions({
    ...(isUnassigned ? { unassigned: true } : { portfolio_id: portfolioId ?? undefined }),
    limit: PAGE_SIZE,
    offset,
  });
  const deleteTransaction = useDeleteInvestmentTransaction();
  // Nome prodotto per riga di movimento (il libro mastro porta solo
  // `asset_id`, mai un'etichetta gia' risolta) — stessa fonte usata
  // ovunque altro per il nome pulito (`display_name ?? name`), mai il
  // simbolo grezzo del parser.
  const assets = useAssets();
  const assetLabel = (assetId: string | null): string | null => {
    if (!assetId) return null;
    const asset = assets.data?.find((a) => a.id === assetId);
    return asset ? asset.display_name ?? asset.name : null;
  };

  if (!isUnassigned && portfolio.isLoading) return <SkeletonRows rows={4} />;
  if (!isUnassigned && portfolio.isError) {
    return (
      <EmptyState
        icon={PiggyBank}
        title="Portfolio non trovato"
        description="Il portfolio richiesto non esiste o non è più disponibile."
        action={<LinkButton to="/investments" size="sm">Torna agli investimenti</LinkButton>}
      />
    );
  }

  const title = isUnassigned ? "Asset senza portfolio" : portfolio.data?.name ?? "";
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

  const confirmDelete = async () => {
    if (!toDelete) return;
    await deleteTransaction.mutateAsync(toDelete.id);
    setToDelete(null);
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div>
        <BackLink to="/investments" label="Investimenti" />
        <h1 className="mt-1 text-lg font-semibold text-text">{title}</h1>
        {isUnassigned && (
          <p className="text-sm text-text-muted">Conti non raggruppati in nessun portfolio.</p>
        )}
        {!isUnassigned && portfolio.data?.description && (
          <p className="text-sm text-text-muted">{portfolio.data.description}</p>
        )}
      </div>

      <PortfolioSummaryBlock scope={scope} />

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4">
        <h3 className="text-sm font-semibold text-text">Asset</h3>
        {positions.isLoading && <SkeletonRows rows={3} />}
        {positions.isError && (
          <ErrorState message="Posizioni non disponibili." onRetry={() => void positions.refetch()} />
        )}
        {positions.data && positions.data.positions.length === 0 && (
          <p className="text-sm text-text-muted">Nessuna posizione aperta in questo ambito.</p>
        )}
        {positions.data && positions.data.positions.length > 0 && (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead className="text-left text-text-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">Asset</th>
                    <th className="px-3 py-2 font-medium">Conto</th>
                    <th className="px-3 py-2 text-right font-medium">Quantità</th>
                    <th className="px-3 py-2 text-right font-medium">Valore attuale</th>
                    <th className="px-3 py-2 text-right font-medium">Rendimento</th>
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
                        <td className="font-numeric px-3 py-2 text-right text-text-muted">{p.quantity}</td>
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
                      <td className="px-3 py-2 text-text">Totale</td>
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
                  <span className="block text-xs font-medium text-text-muted">Totale</span>
                  {formatMoney(positionsTotals.marketValue, positionsTotals.currency)}
                </div>
                <div className={`text-right ${positionsTotals.unrealizedPl >= 0 ? "text-success" : "text-danger"}`}>
                  <span className="block text-xs font-medium text-text-muted">Rendimento</span>
                  {formatSignedMoney(positionsTotals.unrealizedPl, positionsTotals.currency)}
                  {positionsTotalsPct !== null && ` (${formatPercent(positionsTotalsPct, { signed: true })})`}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text">Movimenti</h3>
          <Button size="sm" onClick={() => setTxnDialogOpen(true)}>
            <Plus className="h-4 w-4" /> Nuovo movimento
          </Button>
        </div>

        {transactions.isLoading && <SkeletonRows rows={4} />}
        {transactions.isError && (
          <ErrorState message="Movimenti non disponibili." onRetry={() => void transactions.refetch()} />
        )}
        {transactions.data && transactions.data.length === 0 && offset === 0 && (
          <EmptyState
            icon={PiggyBank}
            title="Nessun movimento"
            description="Acquisti, vendite, dividendi e altri movimenti registrati sui conti di questo ambito appariranno qui."
            action={<Button onClick={() => setTxnDialogOpen(true)}>Registra un movimento</Button>}
          />
        )}
        {transactions.data && transactions.data.length > 0 && (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead className="text-left text-text-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">Data</th>
                    <th className="px-3 py-2 font-medium">Tipo</th>
                    <th className="px-3 py-2 font-medium">Asset</th>
                    <th className="px-3 py-2 text-right font-medium">Importo</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {transactions.data.map((txn) => (
                    <tr key={txn.id} className="border-t border-border">
                      <td className="px-3 py-2 text-text-muted">{formatDate(txn.trade_date)}</td>
                      <td className="px-3 py-2 text-text">{INVESTMENT_TRANSACTION_TYPE_LABELS[txn.type]}</td>
                      <td className="px-3 py-2 text-text">
                        {txn.asset_id ? (
                          <Link to={`/investments/assets/${txn.asset_id}`} state={backState} className="hover:underline">
                            {assetLabel(txn.asset_id) ?? "—"}
                          </Link>
                        ) : (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>
                      <td className="font-numeric px-3 py-2 text-right text-text">
                        {formatSignedMoney(txn.amount, txn.currency)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setToDelete(txn)}
                          aria-label="Elimina movimento"
                          className="hover:text-danger"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="flex flex-col gap-2 md:hidden">
              {transactions.data.map((txn) => (
                <li
                  key={txn.id}
                  className="flex flex-col gap-1 rounded-xl border border-border p-3 text-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-text">{formatDate(txn.trade_date)}</span>
                    <span className="font-numeric text-text">{formatSignedMoney(txn.amount, txn.currency)}</span>
                  </div>
                  <div className="flex items-center justify-between text-text-muted">
                    <span>
                      {INVESTMENT_TRANSACTION_TYPE_LABELS[txn.type]}
                      {txn.asset_id && (
                        <>
                          {" · "}
                          <Link to={`/investments/assets/${txn.asset_id}`} state={backState} className="hover:underline">
                            {assetLabel(txn.asset_id) ?? "—"}
                          </Link>
                        </>
                      )}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setToDelete(txn)}
                      aria-label="Elimina movimento"
                      className="hover:text-danger"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>

            <div className="flex items-center justify-between text-sm text-text-muted">
              <Button
                variant="secondary"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Precedenti
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={transactions.data.length < PAGE_SIZE}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Successivi
              </Button>
            </div>
          </>
        )}
      </div>

      <InvestmentTransactionFormDialog open={txnDialogOpen} onClose={() => setTxnDialogOpen(false)} />

      <Dialog
        open={toDelete !== null}
        onClose={() => setToDelete(null)}
        title="Eliminare il movimento?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setToDelete(null)}>
              Annulla
            </Button>
            <Button variant="danger" loading={deleteTransaction.isPending} onClick={() => void confirmDelete()}>
              Elimina
            </Button>
          </>
        }
      >
        <p className="text-sm text-text-muted">Il movimento verrà rimosso e la posizione ricalcolata.</p>
      </Dialog>
    </div>
  );
}
