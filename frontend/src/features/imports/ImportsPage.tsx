import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, Trash2, UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { usePageToolbar } from "../../components/layout/PageToolbarContext";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { useAccounts } from "../accounts/api";
import { formatDateTime } from "../../lib/format";
import { useTransactionReviewSummary } from "../transactions/api";
import { importsKey, useImportReviewSummary, useImports } from "./api";
import { AiClassificationProgress } from "./AiClassificationProgress";
import { DuplicateReviewDrawer } from "./DuplicateReviewDrawer";
import { ImportDeleteDialog } from "./ImportDeleteDialog";
import { ImportFileViewerDrawer } from "./ImportFileViewerDrawer";
import { ImportRowProgress } from "./ImportRowProgress";
import { ImportWizard } from "./ImportWizard";
import {
  IMPORT_STATUS_TONE,
  isActivelyProcessingImportStatus,
  isActiveAiClassificationStatus,
  useImportStatusLabel,
} from "./labels";
import type { ImportRecord } from "../../types/api";

/** SPEC §43 ("319 classificati, 8 da verificare"): riepilogo mostrato solo
 * a import concluso (import + eventuale classificazione AI, entrambi non
 * piu' attivi) — durante l'elaborazione i numeri cambierebbero ad ogni
 * istante, un conteggio instabile sarebbe piu' fonte di confusione che
 * di aiuto. Link diretto a Movimenti pre-filtrato su questo import. */
function ImportReviewSummary({ importId }: { importId: string }) {
  const { t } = useTranslation("transactions");
  const { data: summary } = useTransactionReviewSummary({ import_id: importId });
  if (!summary || summary.needs_review === 0) return null;
  return (
    <Link to={`/transactions?import=${importId}&review=1`} className="inline-flex w-fit">
      <Badge tone="warning">⚠ {t("page.needsReview", { count: summary.needs_review })}</Badge>
    </Link>
  );
}

/** Transaction Deduplication Engine (docs/SPEC_DEDUP_TRANSACTION.md): badge
 * distinto dalla review di categorizzazione sopra — questa segnala
 * candidati AMBIGUI trovati durante l'import stesso (l'import resta in
 * 'ready_for_review' finche' non sono tutti decisi), non transazioni gia'
 * importate ma incerte nella categoria. */
function DuplicateReviewSummaryBadge({ importId, onClick }: { importId: string; onClick: () => void }) {
  const { t } = useTranslation("imports");
  const { data: summary } = useImportReviewSummary(importId);
  if (!summary || summary.pending === 0) return null;
  return (
    <button type="button" onClick={onClick} className="inline-flex w-fit">
      <Badge tone="warning">⚠ {t("page.duplicatesToReview", { count: summary.pending })}</Badge>
    </button>
  );
}

export function ImportsPage() {
  const { t } = useTranslation("imports");
  const importStatusLabel = useImportStatusLabel();
  const { data: imports, isLoading, isError, refetch } = useImports();
  const { data: accounts } = useAccounts();
  const queryClient = useQueryClient();
  const [wizardOpen, setWizardOpen] = useState(false);
  const [viewingImport, setViewingImport] = useState<ImportRecord | null>(null);
  const [deletingImport, setDeletingImport] = useState<ImportRecord | null>(null);
  const [reviewingImport, setReviewingImport] = useState<ImportRecord | null>(null);
  const accountsById = new Map((accounts ?? []).map((a) => [a.id, a]));

  const importDocumentButton = (
    <Button size="sm" onClick={() => setWizardOpen(true)}>
      <Plus className="h-4 w-4" /> {t("page.importDocument")}
    </Button>
  );
  const toolbarPortal = usePageToolbar(importDocumentButton);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      {toolbarPortal}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text">{t("page.title")}</h1>
        <div className="md:hidden">{importDocumentButton}</div>
      </div>

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState message={t("page.loadError")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && imports && imports.length === 0 && (
        <EmptyState
          icon={UploadCloud}
          title={t("page.empty.title")}
          description={t("page.empty.description")}
          action={<Button onClick={() => setWizardOpen(true)}>{t("page.importDocument")}</Button>}
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
                      {formatDateTime(importRecord.created_at)} ·{" "}
                      {t("page.transactionsImported", { count: importRecord.transactions_imported })}
                      {/* Un import con 0 nuovi (tutti gia' presenti) e' un
                          esito corretto e comune del Deduplication Engine,
                          non un errore — senza questo dettaglio la riga
                          sembrerebbe "non ha fatto nulla". */}
                      {importRecord.transactions_duplicate > 0 &&
                        ` · ${t("page.alreadyPresent", { count: importRecord.transactions_duplicate })}`}
                    </p>
                  )}
                  {importRecord.error_message && <p className="text-sm text-danger">{importRecord.error_message}</p>}
                  {!isLive && showAiProgress && (
                    <AiClassificationProgress
                      importId={importRecord.id}
                      total={importRecord.ai_transactions_total}
                      startedAt={importRecord.completed_at}
                      onSettled={() => queryClient.invalidateQueries({ queryKey: importsKey })}
                    />
                  )}
                  {/* Gap UX reale scoperto testando un'interruzione del
                      provider AI (container spento a meta' import):
                      l'indicatore di progresso spariva silenziosamente non
                      appena lo stato non era piu' pending/running, senza
                      lasciare traccia del perche' fosse fallito. */}
                  {!isLive &&
                    importRecord.ai_classification_status === "failed" &&
                    importRecord.ai_classification_error_message && (
                      <p className="text-sm text-danger">
                        {t("page.aiClassificationFailed", { message: importRecord.ai_classification_error_message })}
                      </p>
                    )}
                  {!isLive && (
                    <div className="mt-1 flex flex-col gap-1">
                      <DuplicateReviewSummaryBadge
                        importId={importRecord.id}
                        onClick={() => setReviewingImport(importRecord)}
                      />
                      {!showAiProgress && <ImportReviewSummary importId={importRecord.id} />}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={IMPORT_STATUS_TONE[importRecord.status]}>
                    {importStatusLabel(importRecord.status)}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setViewingImport(importRecord)}
                    aria-label={t("page.viewOriginalFile")}
                  >
                    <FileText className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setDeletingImport(importRecord)}
                    aria-label={t("page.deleteImport")}
                    disabled={isBlocked}
                    title={
                      isBlocked
                        ? importRecord.ai_classification_status === "running"
                          ? t("page.blockedTooltip.aiRunning")
                          : t("page.blockedTooltip.processing")
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
      <DuplicateReviewDrawer importRecord={reviewingImport} onClose={() => setReviewingImport(null)} />
    </div>
  );
}
