import { useState } from "react";
import { Landmark, Pencil, Plus, Trash2 } from "lucide-react";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Select } from "../../components/ui/Select";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { useAccounts } from "../accounts/api";
import { ACCOUNT_TYPE_LABELS } from "../accounts/labels";
import type { Portfolio } from "../../types/api";
import {
  useAddPortfolioAccount,
  useDeletePortfolio,
  usePortfolioAccounts,
  usePortfolios,
  useRemovePortfolioAccount,
} from "./api";
import { PortfolioFormDialog } from "./PortfolioFormDialog";

/** Gestione dei `Portfolio` (raggruppamenti di conti, mai i conti stessi —
 * ex tab "Conti", contenuto invariato) — da funzione di pari livello nella
 * navigazione a funzione di configurazione secondaria (redesign
 * Investimenti): si usa raramente rispetto a guardare i propri
 * investimenti, e conviveva male con il picker "Vista" che filtra le
 * stesse pagine usando lo stesso sostantivo "portfolio" per due scopi
 * diversi (filtro vs configurazione) — separarli per tipo di superficie
 * (dialog vs pagina) rende la distinzione autoevidente. */
export function PortfolioManageDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const portfolios = usePortfolios();
  const deletePortfolio = useDeletePortfolio();
  const [formOpen, setFormOpen] = useState(false);
  const [editingPortfolio, setEditingPortfolio] = useState<Portfolio | null>(null);
  const [toDelete, setToDelete] = useState<Portfolio | null>(null);

  const confirmDelete = async () => {
    if (!toDelete) return;
    await deletePortfolio.mutateAsync(toDelete.id);
    setToDelete(null);
  };

  return (
    <Dialog open={open} onClose={onClose} title="Gestisci portfolio">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-text-muted">
            Raggruppa più conti sotto un nome. "Tutti i conti" resta sempre disponibile anche senza creare portfolio.
          </p>
          <Button size="sm" onClick={() => setFormOpen(true)}>
            <Plus className="h-4 w-4" /> Nuovo portfolio
          </Button>
        </div>

        {portfolios.isLoading && <SkeletonRows rows={3} />}
        {portfolios.isError && (
          <ErrorState message="Portfolio non disponibili." onRetry={() => void portfolios.refetch()} />
        )}

        {portfolios.data && portfolios.data.length === 0 && (
          <EmptyState
            icon={Landmark}
            title="Nessun portfolio"
            description="Crea un portfolio per raggruppare, ad esempio, Trade Republic e Fineco sotto un unico nome."
            action={<Button onClick={() => setFormOpen(true)}>Nuovo portfolio</Button>}
          />
        )}

        <div className="flex max-h-[50vh] flex-col gap-3 overflow-y-auto">
          {(portfolios.data ?? []).map((portfolio) => (
            <PortfolioCard
              key={portfolio.id}
              portfolio={portfolio}
              onEdit={() => setEditingPortfolio(portfolio)}
              onDelete={() => setToDelete(portfolio)}
            />
          ))}
        </div>
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
    </Dialog>
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
