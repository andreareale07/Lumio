import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import { BottomSheet } from "../../components/ui/BottomSheet";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { formatDate, formatSignedMoney } from "../../lib/format";
import { useIsDesktop } from "../../lib/useIsDesktop";
import type { Transaction } from "../../types/api";
import { useDeleteTransaction } from "./api";

interface Props {
  transaction: Transaction | null;
  onClose: () => void;
  /** Chiamata dopo l'eliminazione riuscita (es. per chiudere il dettaglio). */
  onDeleted: () => void;
}

/** Conferma dell'eliminazione di un singolo movimento: foglio dal basso su smartphone, finestra su
 * desktop. "Annulla" ed "Elimina" hanno lo stesso peso; l'operazione non si puo' annullare. */
export function DeleteTransactionDialog({ transaction, onClose, onDeleted }: Props) {
  const { t } = useTranslation(["transactions", "common"]);
  const isDesktop = useIsDesktop();
  const deleteTransaction = useDeleteTransaction();
  const close = useCallback(() => {
    deleteTransaction.reset();
    onClose();
  }, [deleteTransaction, onClose]);

  if (!transaction) return null;

  const confirm = async () => {
    try {
      await deleteTransaction.mutateAsync(transaction.id);
      deleteTransaction.reset();
      onDeleted();
    } catch {
      // l'errore e' mostrato sotto: la finestra resta aperta per riprovare
    }
  };

  const title = t("transactions:delete.title");
  const content = (
    <div className="flex flex-col gap-3">
      <div className="rounded-lg border border-border p-3">
        <p className="truncate font-medium text-text">{transaction.merchant ?? transaction.description_raw}</p>
        <p className="font-numeric text-sm text-text-muted">
          {formatSignedMoney(transaction.amount, transaction.currency)} · {formatDate(transaction.transaction_date)}
        </p>
      </div>
      <p className="text-sm text-text-muted">{t("transactions:delete.body")}</p>
      <p className="text-sm text-text-muted">{t("transactions:delete.bank")}</p>
      {deleteTransaction.isError && (
        <p role="alert" className="text-sm text-danger">
          {friendlyErrorMessage(deleteTransaction.error, t("transactions:delete.error"))}
        </p>
      )}
    </div>
  );
  const footer = (
    <>
      <Button variant="secondary" onClick={close} className="flex-1 sm:flex-none">
        {t("common:actions.cancel")}
      </Button>
      <Button variant="danger" loading={deleteTransaction.isPending} onClick={() => void confirm()} className="flex-1 sm:flex-none">
        {t("transactions:delete.confirm")}
      </Button>
    </>
  );

  if (!isDesktop) {
    return (
      <BottomSheet open onClose={close} title={title}>
        <div className="pb-2 pt-3">{content}</div>
        <div className="mt-4 flex gap-2">{footer}</div>
      </BottomSheet>
    );
  }
  return (
    <Dialog open onClose={close} title={title} footer={footer}>
      {content}
    </Dialog>
  );
}
