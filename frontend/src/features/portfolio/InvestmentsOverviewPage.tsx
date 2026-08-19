import { useState } from "react";
import { ChevronRight, Plus, Settings } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { formatMoney, formatPercent, formatSignedMoney } from "../../lib/format";
import { AssetFormDialog } from "./AssetFormDialog";
import { InvestmentTransactionFormDialog } from "./InvestmentTransactionFormDialog";
import { PortfolioManageDialog } from "./PortfolioManageDialog";
import { PortfolioSummaryBlock } from "./PortfolioSummaryBlock";
import { PositionManualEditDialog } from "./PositionManualEditDialog";
import { usePortfolioSummaries, usePortfolioValuation } from "./api";
import type { PortfolioSummaryItem } from "../../types/api";

/** Livello 0 del drill-down Investimenti: vista d'insieme di TUTTI i conti
 * (blocco condiviso — vedi `PortfolioSummaryBlock`) piu' l'elenco dei
 * Portfolio, ciascuno un ponte verso lo stesso identico template scoped a
 * un solo raggruppamento (`PortfolioDetailPage`). Nessun tab: un solo
 * flusso verticale, stesso principio della pagina di dettaglio asset che
 * l'utente ha giudicato ben fatta. */
export function InvestmentsOverviewPage() {
  const summaries = usePortfolioSummaries();
  const [manageOpen, setManageOpen] = useState(false);
  const [txnDialogOpen, setTxnDialogOpen] = useState(false);
  const [assetDialogOpen, setAssetDialogOpen] = useState(false);
  const [openingPositionOpen, setOpeningPositionOpen] = useState(false);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-text">Investimenti</h1>
        <Button variant="secondary" size="sm" onClick={() => setManageOpen(true)}>
          <Settings className="h-4 w-4" /> Gestisci portfolio
        </Button>
      </div>

      <PortfolioSummaryBlock scope={{}} />

      <Card className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-text">Portfolio</h3>
        {summaries.isLoading && <SkeletonRows rows={3} />}
        {summaries.isError && (
          <ErrorState message="Portfolio non disponibili." onRetry={() => void summaries.refetch()} />
        )}
        {summaries.data && (
          <ul className="flex flex-col gap-2">
            {summaries.data.items.map((item) => (
              <PortfolioRow key={item.portfolio_id} item={item} />
            ))}
            <UnassignedRow />
          </ul>
        )}
        {summaries.data && summaries.data.items.length === 0 && (
          <p className="text-sm text-text-muted">
            Nessun portfolio ancora — crealo per raggruppare più conti sotto un nome (es. "Trade Republic" e
            "Fineco" insieme).
          </p>
        )}
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => setTxnDialogOpen(true)}>
          <Plus className="h-4 w-4" /> Registra movimento
        </Button>
        <Button variant="secondary" size="sm" onClick={() => setAssetDialogOpen(true)}>
          Nuovo asset
        </Button>
        <Button variant="secondary" size="sm" onClick={() => setOpeningPositionOpen(true)}>
          Carica posizione esistente
        </Button>
      </div>

      <PortfolioManageDialog open={manageOpen} onClose={() => setManageOpen(false)} />
      <InvestmentTransactionFormDialog open={txnDialogOpen} onClose={() => setTxnDialogOpen(false)} />
      <AssetFormDialog open={assetDialogOpen} onClose={() => setAssetDialogOpen(false)} />
      <PositionManualEditDialog open={openingPositionOpen} onClose={() => setOpeningPositionOpen(false)} />
    </div>
  );
}

function PortfolioRow({ item }: { item: PortfolioSummaryItem }) {
  const unrealizedPl = Number(item.unrealized_pl);
  const costBasis = Number(item.cost_basis);
  const pct = costBasis !== 0 ? unrealizedPl / costBasis : null;
  return (
    <li>
      <Link
        to={`/investments/portfolios/${item.portfolio_id}`}
        className="flex items-center justify-between gap-3 rounded-lg border border-border p-3 hover:bg-surface-hover"
      >
        <div>
          <p className="font-medium text-text">{item.name}</p>
          <p className="text-sm text-text-muted">
            {item.account_count} {item.account_count === 1 ? "conto" : "conti"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="font-numeric text-text">{formatMoney(item.market_value, item.currency)}</p>
            {pct !== null && (
              <p className={`font-numeric text-sm ${unrealizedPl >= 0 ? "text-success" : "text-danger"}`}>
                {formatSignedMoney(unrealizedPl, item.currency)} ({formatPercent(pct, { signed: true })})
              </p>
            )}
          </div>
          <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
        </div>
      </Link>
    </li>
  );
}

/** Riga per i conti non raggruppati in nessun Portfolio — pseudo-scope
 * (mai un `Portfolio` vero, nessuna riga nella tabella `portfolios`), ma
 * mostrata con la STESSA forma delle righe reali: cliccandola si apre lo
 * stesso template di dettaglio (`PortfolioDetailPage`) scoped a quei
 * conti. Sempre presente, anche a zero — mai nascosta, altrimenti un
 * conto appena rimosso da un portfolio sparirebbe dalla vista finche' non
 * lo si raggruppa di nuovo da qualche parte. */
function UnassignedRow() {
  const valuation = usePortfolioValuation(null, true);
  if (valuation.isLoading || valuation.isError || !valuation.data) {
    return null; // riga secondaria: nessun errore bloccante se questa sola chiamata fallisce
  }
  const v = valuation.data;
  const unrealizedPl = Number(v.unrealized_pl);
  const costBasis = Number(v.cost_basis);
  const pct = costBasis !== 0 ? unrealizedPl / costBasis : null;
  return (
    <li>
      <Link
        to="/investments/portfolios/unassigned"
        className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-border p-3 hover:bg-surface-hover"
      >
        <div>
          <p className="font-medium text-text">Asset senza portfolio</p>
          <p className="text-sm text-text-muted">Conti non raggruppati in nessun portfolio</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="font-numeric text-text">{formatMoney(v.market_value, v.currency)}</p>
            {pct !== null && v.has_holdings && (
              <p className={`font-numeric text-sm ${unrealizedPl >= 0 ? "text-success" : "text-danger"}`}>
                {formatSignedMoney(unrealizedPl, v.currency)} ({formatPercent(pct, { signed: true })})
              </p>
            )}
          </div>
          <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
        </div>
      </Link>
    </li>
  );
}
