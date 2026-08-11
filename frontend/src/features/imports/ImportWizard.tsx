import { useEffect, useRef, useState } from "react";
import { Check, Circle, Loader2, UploadCloud } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { useAccounts } from "../accounts/api";
import { useTransactions } from "../transactions/api";
import { ApiError } from "../../lib/apiClient";
import { useConfirmImport, useImport, useUploadImport, streamImportEvents, type ImportProgressEvent } from "./api";
import type { ImportUploadResponse } from "../../types/api";

type Step = "upload" | "confirm" | "progress" | "done";
type StageKey = "preparazione" | "estrazione" | "salvataggio";

const MAX_SIZE_MB = 10;

export function ImportWizard({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const { data: accounts } = useAccounts();
  const uploadImport = useUploadImport();
  const confirmImport = useConfirmImport();

  const [step, setStep] = useState<Step>("upload");
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<ImportUploadResponse | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const [stagesDone, setStagesDone] = useState<Record<StageKey, boolean>>({
    preparazione: false,
    estrazione: false,
    salvataggio: false,
  });
  const [warnings, setWarnings] = useState<string[]>([]);
  const [progressError, setProgressError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const { data: importRecord } = useImport(uploadResult?.import.id ?? null);
  const accountForSummary = accounts?.find((a) => a.id === accountId);
  const canLoadSummary = step === "done" && !!importRecord?.period_start;
  const { data: importedTransactions } = useTransactions(
    {
      financial_account_id: importRecord?.financial_account_id,
      date_from: importRecord?.period_start ?? undefined,
      date_to: importRecord?.period_end ?? importRecord?.period_start ?? undefined,
      limit: 500,
    },
    { enabled: canLoadSummary },
  );

  const reset = () => {
    abortRef.current?.abort();
    setStep("upload");
    setAccountId("");
    setFile(null);
    setUploadError(null);
    setUploadResult(null);
    setConfirmError(null);
    setStagesDone({ preparazione: false, estrazione: false, salvataggio: false });
    setWarnings([]);
    setProgressError(null);
  };

  const close = () => {
    reset();
    onClose();
  };

  const onUpload = async () => {
    if (!accountId || !file) return;
    setUploadError(null);
    try {
      const result = await uploadImport.mutateAsync({ accountId, file });
      setUploadResult(result);
      setStep("confirm");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setUploadError("Questo file risulta già importato in questo workspace.");
      } else {
        setUploadError(friendlyErrorMessage(error, "Non è stato possibile caricare il file."));
      }
    }
  };

  const onConfirm = async () => {
    if (!uploadResult) return;
    setConfirmError(null);
    try {
      const mapping =
        uploadResult.import.file_type === "csv" ? uploadResult.preview.suggested_mapping ?? undefined : undefined;
      await confirmImport.mutateAsync({ importId: uploadResult.import.id, mapping });
      setStep("progress");
    } catch (error) {
      setConfirmError(friendlyErrorMessage(error, "Non è stato possibile confermare l'import."));
    }
  };

  useEffect(() => {
    if (step !== "progress" || !uploadResult) return;
    const controller = new AbortController();
    abortRef.current = controller;

    const handleEvent = (event: ImportProgressEvent) => {
      if (event.event === "job.created" || event.event === "job.started") {
        setStagesDone((s) => ({ ...s, preparazione: true }));
      }
      if (event.event === "job.progress" && event.stage === "parsing") {
        setStagesDone((s) => ({ ...s, preparazione: true, estrazione: true }));
      }
      if (event.event === "job.warning" && event.message) {
        setWarnings((w) => [...w, event.message as string]);
      }
      if (event.event === "job.completed") {
        setStagesDone({ preparazione: true, estrazione: true, salvataggio: true });
        setStep("done");
      }
      if (event.event === "job.failed") {
        setProgressError(event.message ?? "L'import non è riuscito.");
      }
    };

    streamImportEvents(uploadResult.import.id, handleEvent, controller.signal).catch(() => {
      // Fallback: useImport(...) sopra continua comunque a fare polling
      // dello stato (SPEC_FE §42) se lo stream si interrompe.
    });

    return () => controller.abort();
  }, [step, uploadResult]);

  // Fallback: se il polling di useImport() segnala completato/fallito prima
  // (o al posto) dello stream, riflette comunque lo stato nella UI.
  useEffect(() => {
    if (!importRecord) return;
    if (importRecord.status === "completed" && step === "progress") {
      setStagesDone({ preparazione: true, estrazione: true, salvataggio: true });
      setStep("done");
    }
    if (importRecord.status === "failed" && step === "progress") {
      setProgressError(importRecord.error_message ?? "L'import non è riuscito.");
    }
  }, [importRecord, step]);

  const categorizedCount = (importedTransactions ?? []).filter((t) => t.category_id !== null).length;

  return (
    <Dialog open={open} onClose={close} title="Importa documento">
      {step === "upload" && (
        <div className="flex flex-col gap-4">
          <Select label="Conto" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Seleziona un conto</option>
            {(accounts ?? []).map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
          <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border p-8 text-center hover:border-primary">
            <UploadCloud className="h-8 w-8 text-text-muted" />
            <span className="text-sm text-text">
              {file ? file.name : "Trascina il file qui oppure seleziona"}
            </span>
            <span className="text-xs text-text-muted">CSV o PDF, max {MAX_SIZE_MB} MB</span>
            <input
              type="file"
              accept=".csv,.pdf"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <p className="text-xs text-text-muted">
            Il file resta memorizzato in locale sul tuo server: nessun dato lascia il tuo ambiente self-hosted.
          </p>
          {uploadError && (
            <p role="alert" className="text-sm text-danger">
              {uploadError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close}>
              Annulla
            </Button>
            <Button onClick={onUpload} loading={uploadImport.isPending} disabled={!accountId || !file}>
              Carica
            </Button>
          </div>
        </div>
      )}

      {step === "confirm" && uploadResult && (
        <div className="flex flex-col gap-4">
          {uploadResult.import.file_type === "pdf" ? (
            <div className="rounded-lg border border-border p-3 text-sm">
              <p className="flex items-center gap-1.5 text-text">
                <Check className="h-4 w-4 text-success" /> PDF valido, documento leggibile
              </p>
              <p className="mt-1 text-text">
                Banca riconosciuta: <strong>{uploadResult.preview.detected_bank_name}</strong>
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-border p-3 text-sm">
              <p className="mb-2 font-medium text-text">Anteprima ({uploadResult.preview.columns.length} colonne)</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr>
                      {uploadResult.preview.columns.map((col) => (
                        <th key={col} className="px-2 py-1 text-left text-text-muted">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {uploadResult.preview.sample_rows.map((row, i) => (
                      <tr key={i}>
                        {row.map((cell, j) => (
                          <td key={j} className="px-2 py-1 text-text">
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {confirmError && (
            <p role="alert" className="text-sm text-danger">
              {confirmError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close}>
              Annulla
            </Button>
            <Button onClick={onConfirm} loading={confirmImport.isPending}>
              Conferma e importa
            </Button>
          </div>
        </div>
      )}

      {step === "progress" && (
        <div className="flex flex-col gap-4">
          <ProgressStep label="Preparazione" done={stagesDone.preparazione} />
          <ProgressStep label="Estrazione" done={stagesDone.estrazione} active={stagesDone.preparazione} />
          <ProgressStep label="Salvataggio" done={stagesDone.salvataggio} active={stagesDone.estrazione} />
          {warnings.length > 0 && (
            <ul className="text-sm text-warning">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
          {progressError && (
            <p role="alert" className="text-sm text-danger">
              {progressError}
            </p>
          )}
        </div>
      )}

      {step === "done" && importRecord && (
        <div className="flex flex-col gap-4">
          <p className="text-lg font-semibold text-text">Import completato</p>
          <p className="text-sm text-text">
            {importRecord.transactions_imported} movimenti importati su {accountForSummary?.name}
            {importedTransactions ? ` — ${categorizedCount} classificati automaticamente` : ""}.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close}>
              Chiudi
            </Button>
            <Button
              onClick={() => {
                navigate(`/transactions?account=${importRecord.financial_account_id}`);
                close();
              }}
            >
              Visualizza movimenti
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}

function ProgressStep({ label, done, active }: { label: string; done: boolean; active?: boolean }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      {done ? (
        <Check className="h-4 w-4 text-success" />
      ) : active ? (
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
      ) : (
        <Circle className="h-4 w-4 text-text-muted" />
      )}
      <span className={done ? "text-text" : "text-text-muted"}>{label}</span>
    </div>
  );
}
