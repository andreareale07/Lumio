import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import type { ImportRecord } from "../../types/api";
import { useDeleteImport, useImportTransactionsCount } from "./api";
import { isTerminalImportStatus } from "./labels";

interface ImportDeleteDialogProps {
  importRecord: ImportRecord | null;
  onClose: () => void;
}

export function ImportDeleteDialog({ importRecord, onClose }: ImportDeleteDialogProps) {
  const isTerminal = importRecord ? isTerminalImportStatus(importRecord.status) : false;
  const count = useImportTransactionsCount(isTerminal ? importRecord?.id ?? null : null);
  const deleteImport = useDeleteImport();

  const handleDelete = async () => {
    if (!importRecord) return;
    try {
      await deleteImport.mutateAsync(importRecord.id);
      onClose();
    } catch {
      // errore mostrato sotto via deleteImport.error, il dialog resta aperto per un retry
    }
  };

  return (
    <Dialog open={!!importRecord} onClose={onClose} title="Eliminare l'import?">
      <p className="text-sm text-text-muted">{importRecord?.filename}</p>

      {importRecord && !isTerminal && (
        <p className="mt-2 text-sm text-text-muted">
          Questo import non ha ancora creato movimenti: verrà prima annullato (se ancora in coda) e poi eliminato
          definitivamente.
        </p>
      )}

      {importRecord && isTerminal && (
        <p className="mt-2 text-sm text-text-muted">
          {count.isLoading && "Verifica delle transazioni collegate…"}
          {count.isError && "L'import e le eventuali transazioni collegate verranno eliminati definitivamente."}
          {count.data && count.data.transactions_count === 0 && "Nessuna transazione collegata a questo import."}
          {count.data && count.data.transactions_count === 1 && "Verrà eliminata 1 transazione collegata a questo import."}
          {count.data &&
            count.data.transactions_count > 1 &&
            `Verranno eliminate ${count.data.transactions_count} transazioni collegate a questo import.`}
          {" "}
          L'operazione non è reversibile.
        </p>
      )}

      {deleteImport.isError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {friendlyErrorMessage(deleteImport.error, "Impossibile eliminare l'import.")}
        </p>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Annulla
        </Button>
        <Button variant="danger" loading={deleteImport.isPending} onClick={() => void handleDelete()}>
          Elimina
        </Button>
      </div>
    </Dialog>
  );
}
