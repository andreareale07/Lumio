import { useState } from "react";
import { Landmark, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Select } from "../../components/ui/Select";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { useAccounts } from "../accounts/api";
import { useAccountTypeLabel } from "../accounts/labels";
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
  const { t } = useTranslation(["portfolio", "common"]);
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
    <Dialog open={open} onClose={onClose} title={t("manageDialog.title")}>
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-text-muted">{t("manageDialog.description")}</p>
          <Button size="sm" onClick={() => setFormOpen(true)}>
            <Plus className="h-4 w-4" /> {t("manageDialog.newPortfolio")}
          </Button>
        </div>

        {portfolios.isLoading && <SkeletonRows rows={3} />}
        {portfolios.isError && (
          <ErrorState message={t("manageDialog.loadError")} onRetry={() => void portfolios.refetch()} />
        )}

        {portfolios.data && portfolios.data.length === 0 && (
          <EmptyState
            icon={Landmark}
            title={t("manageDialog.empty.title")}
            description={t("manageDialog.empty.description")}
            action={<Button onClick={() => setFormOpen(true)}>{t("manageDialog.newPortfolio")}</Button>}
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
        title={t("manageDialog.deleteDialog.title")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setToDelete(null)}>
              {t("common:actions.cancel")}
            </Button>
            <Button variant="danger" loading={deletePortfolio.isPending} onClick={() => void confirmDelete()}>
              {t("manageDialog.deletePortfolio")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-text-muted">
          {t("manageDialog.deleteDialog.body", { name: toDelete?.name })}
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
  const { t } = useTranslation("portfolio");
  const accountTypeLabel = useAccountTypeLabel();
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
          <Button variant="ghost" size="icon" onClick={onEdit} aria-label={t("manageDialog.editPortfolio")}>
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onDelete}
            aria-label={t("manageDialog.deletePortfolio")}
            className="hover:text-danger"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {links.isLoading && <SkeletonRows rows={2} />}
      {links.data && links.data.length === 0 && (
        <p className="text-sm text-text-muted">{t("manageDialog.noLinkedAccounts")}</p>
      )}
      {links.data && links.data.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {links.data.map((link) => {
            const account = (accounts ?? []).find((a) => a.id === link.financial_account_id);
            return (
              <Badge key={link.id} tone="primary">
                {account?.name ?? t("manageDialog.defaultAccountName")}
                <button
                  type="button"
                  onClick={() => removeAccount.mutate(link.financial_account_id)}
                  aria-label={t("manageDialog.removeAccount", {
                    name: account?.name ?? t("manageDialog.defaultAccountName").toLowerCase(),
                  })}
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
            aria-label={t("manageDialog.addAccountLabel")}
            value={selectedAccountId}
            onChange={(e) => setSelectedAccountId(e.target.value)}
            className="w-auto"
          >
            <option value="">{t("manageDialog.selectAccount")}</option>
            {availableAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name} · {accountTypeLabel(account.account_type)}
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
            {t("manageDialog.add")}
          </Button>
        </div>
      )}
    </Card>
  );
}
