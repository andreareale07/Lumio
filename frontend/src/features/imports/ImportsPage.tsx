import { useState } from "react";
import { Plus, UploadCloud } from "lucide-react";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { useAccounts } from "../accounts/api";
import { formatDateTime } from "../../lib/format";
import { useImports } from "./api";
import { ImportWizard } from "./ImportWizard";
import { IMPORT_STATUS_LABELS, IMPORT_STATUS_TONE } from "./labels";

export function ImportsPage() {
  const { data: imports, isLoading, isError, refetch } = useImports();
  const { data: accounts } = useAccounts();
  const [wizardOpen, setWizardOpen] = useState(false);
  const accountsById = new Map((accounts ?? []).map((a) => [a.id, a]));

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text">Import</h1>
        <Button size="sm" onClick={() => setWizardOpen(true)}>
          <Plus className="h-4 w-4" /> Importa documento
        </Button>
      </div>

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState message="Non siamo riusciti a caricare gli import." onRetry={() => void refetch()} />}

      {!isLoading && !isError && imports && imports.length === 0 && (
        <EmptyState
          icon={UploadCloud}
          title="Nessuna importazione"
          description="Importa un estratto conto CSV o PDF per popolare i tuoi movimenti."
          action={<Button onClick={() => setWizardOpen(true)}>Importa documento</Button>}
        />
      )}

      {!isLoading && !isError && imports && imports.length > 0 && (
        <div className="flex flex-col gap-2">
          {imports.map((importRecord) => (
            <Card key={importRecord.id} className="flex items-center justify-between gap-3">
              <div>
                <p className="font-medium text-text">
                  {accountsById.get(importRecord.financial_account_id)?.name ?? importRecord.filename}
                </p>
                <p className="text-sm text-text-muted">
                  {formatDateTime(importRecord.created_at)} · {importRecord.transactions_imported} movimenti
                </p>
                {importRecord.error_message && <p className="text-sm text-danger">{importRecord.error_message}</p>}
              </div>
              <Badge tone={IMPORT_STATUS_TONE[importRecord.status]}>
                {IMPORT_STATUS_LABELS[importRecord.status]}
              </Badge>
            </Card>
          ))}
        </div>
      )}

      <ImportWizard open={wizardOpen} onClose={() => setWizardOpen(false)} />
    </div>
  );
}
