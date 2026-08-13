import { useMemo, useState } from "react";
import { Landmark, Pencil, PiggyBank, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DonutChart } from "../../components/charts/DonutChart";
import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { JobRunStatus } from "../../components/ui/JobRunStatus";
import { Select } from "../../components/ui/Select";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { Tabs } from "../../components/ui/Tabs";
import { formatDate, formatMoney, formatPercent, formatSignedMoney } from "../../lib/format";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import { useAccounts } from "../accounts/api";
import { ACCOUNT_TYPE_LABELS } from "../accounts/labels";
import type { InvestmentTransaction, Portfolio, Position } from "../../types/api";
import { AssetFormDialog } from "./AssetFormDialog";
import { InvestmentTransactionFormDialog } from "./InvestmentTransactionFormDialog";
import { PortfolioFormDialog } from "./PortfolioFormDialog";
import { PositionManualEditDialog } from "./PositionManualEditDialog";
import {
  useAddPortfolioAccount,
  useAssets,
  useDeleteInvestmentTransaction,
  useDeletePortfolio,
  useInvestmentTransactions,
  usePortfolioAccounts,
  usePortfolioAllocation,
  usePortfolioPerformance,
  usePortfolios,
  usePortfolioValuation,
  usePositions,
  useRemovePortfolioAccount,
  useSnapshotRebuildStatus,
  useTriggerSnapshotRebuild,
} from "./api";
import { INVESTMENT_TRANSACTION_TYPE_LABELS } from "./labels";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "positions", label: "Posizioni" },
  { key: "movements", label: "Movimenti" },
  { key: "allocation", label: "Allocation" },
  { key: "performance", label: "Performance" },
  { key: "accounts", label: "Conti" },
];

export function InvestmentsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") ?? "overview";
  const portfolioId = searchParams.get("portfolio") ?? "";

  const setTab = (next: string) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params);
  };
  const setPortfolioId = (next: string) => {
    const params = new URLSearchParams(searchParams);
    if (next) params.set("portfolio", next);
    else params.delete("portfolio");
    setSearchParams(params);
  };

  const { data: portfolios } = usePortfolios();
  const portfolioAccounts = usePortfolioAccounts(portfolioId || null);
  // "Tutti i conti" (nessun portfolio selezionato) resta la vista implicita
  // di default (SPEC §36) — nessun filtro applicato in quel caso.
  const accountIdsInScope = useMemo(
    () => (portfolioId ? new Set(portfolioAccounts.data?.map((l) => l.financial_account_id)) : null),
    [portfolioId, portfolioAccounts.data],
  );

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-text">Investimenti</h1>
        <Select
          aria-label="Portfolio"
          value={portfolioId}
          onChange={(e) => setPortfolioId(e.target.value)}
          className="w-auto"
        >
          <option value="">Tutti i conti</option>
          {(portfolios ?? []).map((portfolio) => (
            <option key={portfolio.id} value={portfolio.id}>
              {portfolio.name}
            </option>
          ))}
        </Select>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" && (
        <OverviewTab portfolioId={portfolioId || null} onNewMovement={() => setTab("movements")} />
      )}
      {tab === "positions" && <PositionsTab accountIdsInScope={accountIdsInScope} />}
      {tab === "movements" && <MovementsTab accountIdsInScope={accountIdsInScope} />}
      {tab === "allocation" && <AllocationTab portfolioId={portfolioId || null} />}
      {tab === "performance" && <PerformanceTab portfolioId={portfolioId || null} />}
      {tab === "accounts" && <PortfoliosTab />}
    </div>
  );
}

// --- Overview ----------------------------------------------------------------

function OverviewTab({
  portfolioId,
  onNewMovement,
}: {
  portfolioId: string | null;
  onNewMovement: () => void;
}) {
  const valuation = usePortfolioValuation(portfolioId);
  const [formOpen, setFormOpen] = useState(false);

  if (valuation.isLoading) return <SkeletonRows rows={4} />;
  if (valuation.isError) {
    return (
      <ErrorState
        message="Non siamo riusciti a caricare i tuoi investimenti."
        onRetry={() => void valuation.refetch()}
      />
    );
  }

  const data = valuation.data;
  if (!data || (!data.has_holdings && data.cost_basis === "0.00")) {
    return (
      <>
        <EmptyState
          icon={PiggyBank}
          title="Non hai ancora aggiunto investimenti"
          description="Registra un movimento (acquisto, versamento...) o carica una posizione già esistente per iniziare a tracciare il tuo portafoglio."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button onClick={() => setFormOpen(true)}>Registra un movimento</Button>
            </div>
          }
        />
        <InvestmentTransactionFormDialog open={formOpen} onClose={() => setFormOpen(false)} />
      </>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">
            {data.has_market_data ? "Valore di mercato" : "Valore a costo"}
          </h3>
          <span className="font-numeric text-xl font-semibold text-text">
            {formatMoney(data.market_value, data.currency)}
          </span>
        </Card>
        <Card className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">P/L non realizzato</h3>
          <span className="font-numeric text-xl font-semibold text-text">
            {formatSignedMoney(data.unrealized_pl, data.currency)}
          </span>
        </Card>
        <Card className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">P/L realizzato</h3>
          <span className="font-numeric text-xl font-semibold text-text">
            {formatSignedMoney(data.realized_pl, data.currency)}
          </span>
          <button
            type="button"
            onClick={onNewMovement}
            className="text-left text-sm font-medium text-primary hover:underline"
          >
            Registra un nuovo movimento
          </button>
        </Card>
      </div>
      {!data.has_market_data && (
        <p className="text-sm text-text-muted">
          Alcune posizioni sono valorizzate al costo storico: nessun prezzo di mercato disponibile. Configura
          un provider in{" "}
          <a href="/settings/market-data" className="font-medium text-primary hover:underline">
            Market Data
          </a>{" "}
          o inserisci un prezzo manuale sull'asset.
        </p>
      )}
    </div>
  );
}

// --- Allocation ------------------------------------------------------------

function AllocationTab({ portfolioId }: { portfolioId: string | null }) {
  const allocation = usePortfolioAllocation(portfolioId);

  if (allocation.isLoading) return <SkeletonRows rows={4} />;
  if (allocation.isError) {
    return <ErrorState message="Allocation non disponibile." onRetry={() => void allocation.refetch()} />;
  }

  const data = allocation.data;
  const isEmpty = !data || data.by_asset.length === 0;

  if (isEmpty) {
    return (
      <EmptyState
        icon={PiggyBank}
        title="Nessuna posizione da distribuire"
        description="L'allocation appare non appena hai almeno una posizione con quantità diversa da zero."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {!data.has_market_data && (
        <p className="text-sm text-text-muted">
          Distribuzione calcolata al costo storico dove manca un prezzo di mercato.
        </p>
      )}
      <ChartCard
        title="Per tipo di strumento"
        tableCaption="Allocation per tipo di strumento"
        tableHeaders={["Tipo", "Valore", "Quota"]}
        tableRows={data.by_asset_type.map((item) => [
          item.label,
          formatMoney(item.value, data.currency),
          formatPercent(item.share),
        ])}
      >
        <DonutChart
          currency={data.currency}
          data={data.by_asset_type.map((item) => ({ label: item.label, value: Number(item.value) }))}
        />
      </ChartCard>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Per asset</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {data.by_asset.map((item) => (
              <li key={item.key} className="flex items-center justify-between text-text-muted">
                <span>{item.label}</span>
                <span className="font-numeric text-text">
                  {formatMoney(item.value, data.currency)} · {formatPercent(item.share)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-text">Per conto</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {data.by_account.map((item) => (
              <li key={item.key} className="flex items-center justify-between text-text-muted">
                <span>{item.label}</span>
                <span className="font-numeric text-text">
                  {formatMoney(item.value, data.currency)} · {formatPercent(item.share)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

// --- Performance -------------------------------------------------------------

function PerformanceTab({ portfolioId }: { portfolioId: string | null }) {
  const { trendWindow } = usePeriodNavigator({ granularities: ["month", "quarter", "semester", "year"] });

  // L'endpoint /portfolios/analytics/performance non bucketizza (ritorna
  // sempre la serie giornaliera grezza degli snapshot nel range, vedi
  // `portfolio_analytics.py::list_portfolio_snapshots`) — la granularita'
  // del navigator qui controlla solo l'AMPIEZZA della finestra navigabile
  // (mese/trimestre/semestre/anno), non il bucketing dei punti sul grafico.
  const performance = usePortfolioPerformance({
    portfolio_id: portfolioId ?? undefined,
    date_from: trendWindow.date_from,
    date_to: trendWindow.date_to,
  });
  const rebuildSnapshot = useTriggerSnapshotRebuild();
  const rebuildStatus = useSnapshotRebuildStatus();

  const onRebuildNow = async () => {
    await rebuildSnapshot.mutateAsync();
    // Stesso principio di MarketDataSettingsPage: nessun canale di
    // progresso live, si ri-legge lo stato persistente (sopravvive a un
    // refresh pagina) dopo che il worker ha avuto il tempo di scriverlo.
    setTimeout(() => {
      void performance.refetch();
      void rebuildStatus.refetch();
    }, 1500);
  };

  if (performance.isLoading) return <SkeletonRows rows={4} />;
  if (performance.isError) {
    return <ErrorState message="Performance non disponibile." onRetry={() => void performance.refetch()} />;
  }

  const points = performance.data?.points ?? [];
  const currency = performance.data?.currency ?? "EUR";
  const trendPoints = points.map((p) => ({
    period: p.snapshot_date,
    label: formatDate(p.snapshot_date),
    value: Number(p.market_value),
  }));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PeriodNavigator granularities={["month", "quarter", "semester", "year"]} />
        <Button variant="secondary" size="sm" loading={rebuildSnapshot.isPending} onClick={() => void onRebuildNow()}>
          <RefreshCw className="h-4 w-4" /> Ricalcola adesso
        </Button>
      </div>
      <JobRunStatus run={rebuildStatus.data} />

      <ChartCard
        title="Valore nel tempo"
        empty={trendPoints.length === 0}
        emptyState={
          <EmptyState
            icon={PiggyBank}
            title="Nessuno storico ancora"
            description="Lo storico si costruisce giorno per giorno dallo snapshot automatico — usa 'Ricalcola adesso' per crearne subito uno."
          />
        }
        tableCaption="Valore del portfolio nel tempo"
        tableHeaders={["Data", "Valore"]}
        tableRows={trendPoints.map((p) => [p.label, formatMoney(p.value, currency)])}
      >
        <AreaTrendChart data={trendPoints} currency={currency} />
      </ChartCard>
    </div>
  );
}

// --- Posizioni -----------------------------------------------------------

function PositionsTab({ accountIdsInScope }: { accountIdsInScope: Set<string> | null }) {
  const [showClosed, setShowClosed] = useState(false);
  const positions = usePositions(showClosed ? { only_open: false } : {});
  const { data: accounts } = useAccounts();
  const { data: assets } = useAssets();
  const [assetFormOpen, setAssetFormOpen] = useState(false);
  const [editingPosition, setEditingPosition] = useState<Position | null | undefined>(undefined);

  const accountsById = useMemo(() => new Map((accounts ?? []).map((a) => [a.id, a])), [accounts]);
  const assetsById = useMemo(() => new Map((assets ?? []).map((a) => [a.id, a])), [assets]);

  if (positions.isLoading) return <SkeletonRows rows={4} />;
  if (positions.isError) {
    return <ErrorState message="Posizioni non disponibili." onRetry={() => void positions.refetch()} />;
  }

  const scoped = (positions.data ?? []).filter(
    (p) => !accountIdsInScope || accountIdsInScope.has(p.financial_account_id),
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm text-text-muted">
          <input
            type="checkbox"
            checked={showClosed}
            onChange={(e) => setShowClosed(e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          Mostra posizioni chiuse
        </label>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setAssetFormOpen(true)}>
            <Plus className="h-4 w-4" /> Nuovo asset
          </Button>
          <Button size="sm" onClick={() => setEditingPosition(null)}>
            <Plus className="h-4 w-4" /> Posizione iniziale
          </Button>
        </div>
      </div>

      {scoped.length === 0 && (
        <EmptyState
          icon={PiggyBank}
          title="Nessuna posizione"
          description="Le posizioni derivano automaticamente dai movimenti registrati, oppure puoi caricarne una già esistente."
        />
      )}

      {scoped.length > 0 && (
        <>
          <div className="hidden overflow-hidden rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead className="bg-surface-hover text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Asset</th>
                  <th className="px-3 py-2 font-medium">Conto</th>
                  <th className="px-3 py-2 text-right font-medium">Quantità</th>
                  <th className="px-3 py-2 text-right font-medium">Costo medio</th>
                  <th className="px-3 py-2 text-right font-medium">Valore a costo</th>
                  <th className="px-3 py-2 text-right font-medium">P/L realizzato</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {scoped.map((position) => {
                  const asset = assetsById.get(position.asset_id);
                  const account = accountsById.get(position.financial_account_id);
                  const value = Number(position.quantity) * Number(position.average_cost);
                  return (
                    <tr key={position.id} className="border-t border-border bg-surface">
                      <td className="px-3 py-2 text-text">{asset ? (asset.symbol ?? asset.name) : "—"}</td>
                      <td className="px-3 py-2 text-text-muted">{account?.name ?? "—"}</td>
                      <td className="font-numeric px-3 py-2 text-right text-text">{position.quantity}</td>
                      <td className="font-numeric px-3 py-2 text-right text-text">
                        {formatMoney(position.average_cost, position.currency)}
                      </td>
                      <td className="font-numeric px-3 py-2 text-right text-text">
                        {formatMoney(value, position.currency)}
                      </td>
                      <td className="font-numeric px-3 py-2 text-right text-text">
                        {formatSignedMoney(position.realized_pl, position.currency)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => setEditingPosition(position)}
                          className="text-sm text-text-muted hover:text-text"
                        >
                          Modifica
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-2 md:hidden">
            {scoped.map((position) => {
              const asset = assetsById.get(position.asset_id);
              const account = accountsById.get(position.financial_account_id);
              const value = Number(position.quantity) * Number(position.average_cost);
              return (
                <button
                  key={position.id}
                  onClick={() => setEditingPosition(position)}
                  className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-3 text-left"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-text">{asset ? (asset.symbol ?? asset.name) : "—"}</span>
                    <span className="font-numeric text-text">{formatMoney(value, position.currency)}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm text-text-muted">
                    <span>{account?.name ?? "—"}</span>
                    <span>{position.quantity} · media {formatMoney(position.average_cost, position.currency)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </>
      )}

      <AssetFormDialog open={assetFormOpen} onClose={() => setAssetFormOpen(false)} />
      <PositionManualEditDialog
        open={editingPosition !== undefined}
        onClose={() => setEditingPosition(undefined)}
        position={editingPosition}
      />
    </div>
  );
}

// --- Movimenti -----------------------------------------------------------

function MovementsTab({ accountIdsInScope }: { accountIdsInScope: Set<string> | null }) {
  const transactions = useInvestmentTransactions({ limit: 200 });
  const { data: accounts } = useAccounts();
  const { data: assets } = useAssets();
  const deleteTransaction = useDeleteInvestmentTransaction();
  const [formOpen, setFormOpen] = useState(false);
  const [toDelete, setToDelete] = useState<InvestmentTransaction | null>(null);

  const accountsById = useMemo(() => new Map((accounts ?? []).map((a) => [a.id, a])), [accounts]);
  const assetsById = useMemo(() => new Map((assets ?? []).map((a) => [a.id, a])), [assets]);

  if (transactions.isLoading) return <SkeletonRows rows={6} />;
  if (transactions.isError) {
    return <ErrorState message="Movimenti non disponibili." onRetry={() => void transactions.refetch()} />;
  }

  const scoped = (transactions.data ?? []).filter(
    (t) => !accountIdsInScope || accountIdsInScope.has(t.financial_account_id),
  );

  const confirmDelete = async () => {
    if (!toDelete) return;
    await deleteTransaction.mutateAsync(toDelete.id);
    setToDelete(null);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setFormOpen(true)}>
          <Plus className="h-4 w-4" /> Nuovo movimento
        </Button>
      </div>

      {scoped.length === 0 && (
        <EmptyState
          icon={PiggyBank}
          title="Nessun movimento"
          description="Acquisti, vendite, dividendi e altri movimenti degli investimenti appariranno qui."
          action={<Button onClick={() => setFormOpen(true)}>Registra un movimento</Button>}
        />
      )}

      {scoped.length > 0 && (
        <>
          <div className="hidden overflow-hidden rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead className="bg-surface-hover text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Data</th>
                  <th className="px-3 py-2 font-medium">Tipo</th>
                  <th className="px-3 py-2 font-medium">Asset</th>
                  <th className="px-3 py-2 font-medium">Conto</th>
                  <th className="px-3 py-2 text-right font-medium">Importo</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {scoped.map((txn) => {
                  const asset = txn.asset_id ? assetsById.get(txn.asset_id) : undefined;
                  const account = accountsById.get(txn.financial_account_id);
                  return (
                    <tr key={txn.id} className="border-t border-border bg-surface">
                      <td className="px-3 py-2 text-text-muted">{formatDate(txn.trade_date)}</td>
                      <td className="px-3 py-2 text-text">{INVESTMENT_TRANSACTION_TYPE_LABELS[txn.type]}</td>
                      <td className="px-3 py-2 text-text-muted">{asset ? (asset.symbol ?? asset.name) : "—"}</td>
                      <td className="px-3 py-2 text-text-muted">{account?.name ?? "—"}</td>
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
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-2 md:hidden">
            {scoped.map((txn) => {
              const asset = txn.asset_id ? assetsById.get(txn.asset_id) : undefined;
              const account = accountsById.get(txn.financial_account_id);
              return (
                <div key={txn.id} className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-3">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-text">{INVESTMENT_TRANSACTION_TYPE_LABELS[txn.type]}</span>
                    <span className="font-numeric text-text">{formatSignedMoney(txn.amount, txn.currency)}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm text-text-muted">
                    <span>{asset ? (asset.symbol ?? asset.name) : account?.name ?? "—"}</span>
                    <span>{formatDate(txn.trade_date)}</span>
                  </div>
                  <Button variant="link" size="sm" onClick={() => setToDelete(txn)} className="self-end !text-danger">
                    Elimina
                  </Button>
                </div>
              );
            })}
          </div>
        </>
      )}

      <InvestmentTransactionFormDialog open={formOpen} onClose={() => setFormOpen(false)} />

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
        <p className="text-sm text-text-muted">
          La posizione verrà ricalcolata escludendo questo movimento. L'operazione non è reversibile.
        </p>
      </Dialog>
    </div>
  );
}

// --- Conti (portfolio aggregabili, SPEC §36) --------------------------------

function PortfoliosTab() {
  const portfolios = usePortfolios();
  const deletePortfolio = useDeletePortfolio();
  const [formOpen, setFormOpen] = useState(false);
  const [editingPortfolio, setEditingPortfolio] = useState<Portfolio | null>(null);
  const [toDelete, setToDelete] = useState<Portfolio | null>(null);

  if (portfolios.isLoading) return <SkeletonRows rows={3} />;
  if (portfolios.isError) {
    return <ErrorState message="Portfolio non disponibili." onRetry={() => void portfolios.refetch()} />;
  }

  const confirmDelete = async () => {
    if (!toDelete) return;
    await deletePortfolio.mutateAsync(toDelete.id);
    setToDelete(null);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-muted">
          Raggruppa più conti sotto un nome. "Tutti i conti" resta sempre disponibile anche senza creare portfolio.
        </p>
        <Button size="sm" onClick={() => setFormOpen(true)}>
          <Plus className="h-4 w-4" /> Nuovo portfolio
        </Button>
      </div>

      {(portfolios.data ?? []).length === 0 && (
        <EmptyState
          icon={Landmark}
          title="Nessun portfolio"
          description="Crea un portfolio per raggruppare, ad esempio, Trade Republic e Fineco sotto un unico nome."
          action={<Button onClick={() => setFormOpen(true)}>Nuovo portfolio</Button>}
        />
      )}

      <div className="flex flex-col gap-3">
        {(portfolios.data ?? []).map((portfolio) => (
          <PortfolioCard
            key={portfolio.id}
            portfolio={portfolio}
            onEdit={() => setEditingPortfolio(portfolio)}
            onDelete={() => setToDelete(portfolio)}
          />
        ))}
      </div>

      <PortfolioFormDialog open={formOpen} onClose={() => setFormOpen(false)} />
      <PortfolioFormDialog
        open={editingPortfolio !== null}
        onClose={() => setEditingPortfolio(null)}
        portfolio={editingPortfolio}
      />

      <Dialog
        open={toDelete !== null}
        onClose={() => setToDelete(null)}
        title="Eliminare il portfolio?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setToDelete(null)}>
              Annulla
            </Button>
            <Button variant="danger" loading={deletePortfolio.isPending} onClick={() => void confirmDelete()}>
              Elimina
            </Button>
          </>
        }
      >
        <p className="text-sm text-text-muted">
          I conti restano intatti: viene eliminato solo il raggruppamento "{toDelete?.name}".
        </p>
      </Dialog>
    </div>
  );
}

function PortfolioCard({
  portfolio,
  onEdit,
  onDelete,
}: {
  portfolio: Portfolio;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { data: accounts } = useAccounts();
  const links = usePortfolioAccounts(portfolio.id);
  const addAccount = useAddPortfolioAccount(portfolio.id);
  const removeAccount = useRemovePortfolioAccount(portfolio.id);
  const [selectedAccountId, setSelectedAccountId] = useState("");

  const linkedAccountIds = new Set((links.data ?? []).map((l) => l.financial_account_id));
  const availableAccounts = (accounts ?? []).filter((a) => !linkedAccountIds.has(a.id));

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-semibold text-text">{portfolio.name}</p>
          {portfolio.description && <p className="text-sm text-text-muted">{portfolio.description}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="icon" onClick={onEdit} aria-label="Modifica portfolio">
            <Pencil className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onDelete} aria-label="Elimina portfolio" className="hover:text-danger">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {links.isLoading && <SkeletonRows rows={2} />}
      {links.data && links.data.length === 0 && (
        <p className="text-sm text-text-muted">Nessun conto associato.</p>
      )}
      {links.data && links.data.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {links.data.map((link) => {
            const account = (accounts ?? []).find((a) => a.id === link.financial_account_id);
            return (
              <Badge key={link.id} tone="primary">
                {account?.name ?? "Conto"}
                <button
                  type="button"
                  onClick={() => removeAccount.mutate(link.financial_account_id)}
                  aria-label={`Rimuovi ${account?.name ?? "conto"}`}
                  className="ml-1 hover:text-danger"
                >
                  ×
                </button>
              </Badge>
            );
          })}
        </div>
      )}

      {availableAccounts.length > 0 && (
        <div className="flex items-end gap-2">
          <Select
            aria-label="Aggiungi conto"
            value={selectedAccountId}
            onChange={(e) => setSelectedAccountId(e.target.value)}
            className="w-auto"
          >
            <option value="">Seleziona un conto</option>
            {availableAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name} · {ACCOUNT_TYPE_LABELS[account.account_type]}
              </option>
            ))}
          </Select>
          <Button
            variant="secondary"
            size="sm"
            disabled={!selectedAccountId}
            loading={addAccount.isPending}
            onClick={() => {
              addAccount.mutate(selectedAccountId);
              setSelectedAccountId("");
            }}
          >
            Aggiungi
          </Button>
        </div>
      )}
    </Card>
  );
}

