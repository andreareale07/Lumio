import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, Trash2, UploadCloud } from "lucide-react";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { useAccounts } from "../accounts/api";
import { formatDateTime } from "../../lib/format";
import { importsKey, useImports } from "./api";
import { AiClassificationProgress } from "./AiClassificationProgress";
import { ImportDeleteDialog } from "./ImportDeleteDialog";
import { ImportFileViewerDrawer } from "./ImportFileViewerDrawer";
import { ImportRowProgress } from "./ImportRowProgress";
import { ImportWizard } from "./ImportWizard";
import {
  IMPORT_STATUS_LABELS,
  IMPORT_STATUS_TONE,
  isActivelyProcessingImportStatus,
  isActiveAiClassificationStatus,
} from "./labels";
import type { ImportRecord } from "../../types/api";

export function ImportsPage() {
  const { data: imports, isLoading, isError, refetch } = useImports();
  const { data: accounts } = useAccounts();
  const queryClient = useQueryClient();
  const [wizardOpen, setWizardOpen] = useState(false);
  const [viewingImport, setViewingImport] = useState<ImportRecord | null>(null);
  const [deletingImport, setDeletingImport] = useState<ImportRecord | null>(null);
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
          {imports.map((importRecord) => {
            const isLive = importRecord.status === "queued" || importRecord.status === "processing" || importRecord.status === "parsing";
            const isBlocked =
              isActivelyProcessingImportStatus(importRecord.status) ||
              importRecord.ai_classification_status === "running";
            const showAiProgress = isActiveAiClassificationStatus(importRecord.ai_classification_status);
            return (
              <Card key={importRecord.id} className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-text">
                    {accountsById.get(importRecord.financial_account_id)?.name ?? importRecord.filename}
                  </p>
                  {isLive ? (
                    <ImportRowProgress
                      importId={importRecord.id}
                      onSettled={() => queryClient.invalidateQueries({ queryKey: importsKey })}
                    />
                  ) : (
                    <p className="text-sm text-text-muted">
                      {formatDateTime(importRecord.created_at)} · {importRecord.transactions_imported} movimenti
                    </p>
                  )}
                  {importRecord.error_message && <p className="text-sm text-danger">{importRecord.error_message}</p>}
                  {!isLive && showAiProgress && (
                    <AiClassificationProgress
                      importId={importRecord.id}
                      total={importRecord.ai_transactions_total}
                      onSettled={() => queryClient.invalidateQueries({ queryKey: importsKey })}
                    />
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={IMPORT_STATUS_TONE[importRecord.status]}>
                    {IMPORT_STATUS_LABELS[importRecord.status]}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setViewingImport(importRecord)}
                    aria-label="Visualizza file originale"
                  >
                    <FileText className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setDeletingImport(importRecord)}
                    aria-label="Elimina import"
                    disabled={isBlocked}
                    title={
                      isBlocked
                        ? importRecord.ai_classification_status === "running"
                          ? "Classificazione AI in corso: attendi il completamento prima di poterlo eliminare"
                          : "Import in elaborazione: attendi il completamento prima di poterlo eliminare"
                        : undefined
                    }
                    className="hover:text-danger"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <ImportWizard open={wizardOpen} onClose={() => setWizardOpen(false)} />
      <ImportFileViewerDrawer importRecord={viewingImport} onClose={() => setViewingImport(null)} />
      <ImportDeleteDialog importRecord={deletingImport} onClose={() => setDeletingImport(null)} />
    </div>
  );
}
