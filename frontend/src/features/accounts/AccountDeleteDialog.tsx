import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { useTransactionReviewSummary } from "../transactions/api";
import type { FinancialAccount } from "../../types/api";
import { useDeleteAccount } from "./api";

interface AccountDeleteDialogProps {
  account: FinancialAccount | null;
  onClose: (deleted?: boolean) => void;
}

export function AccountDeleteDialog({ account, onClose }: AccountDeleteDialogProps) {
  const { t } = useTranslation(["accounts", "common"]);
  const summary = useTransactionReviewSummary(
    { financial_account_id: account?.id },
    { enabled: !!account },
  );
  const deleteAccount = useDeleteAccount();

  const handleDelete = async () => {
    if (!account) return;
    try {
      await deleteAccount.mutateAsync(account.id);
      onClose(true);
    } catch {
      // errore mostrato sotto via deleteAccount.error, il dialog resta aperto per un retry
    }
  };

  return (
    <Dialog open={!!account} onClose={onClose} title={t("accounts:deleteDialog.title")}>
      <p className="text-sm text-text-muted">{account?.name}</p>

      <p className="mt-2 text-sm text-text-muted">
        {summary.isLoading && t("accounts:deleteDialog.checkingCount")}
        {summary.isError && t("accounts:deleteDialog.countError")}
        {summary.data &&
          (summary.data.total === 0
            ? t("accounts:deleteDialog.noTransactions")
            : t("accounts:deleteDialog.transactionsCount", { count: summary.data.total }))}
        {" "}
        {t("accounts:deleteDialog.irreversible")}
      </p>

      {deleteAccount.isError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {friendlyErrorMessage(deleteAccount.error, t("accounts:deleteDialog.error"))}
        </p>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={() => onClose()}>
          {t("common:actions.cancel")}
        </Button>
        <Button variant="danger" loading={deleteAccount.isPending} onClick={() => void handleDelete()}>
          {t("accounts:deleteDialog.confirm")}
        </Button>
      </div>
    </Dialog>
  );
}
