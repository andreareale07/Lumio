import { useEffect, useRef, useState } from "react";
import { Check, Circle, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import type { GoogleIntegration } from "../../../types/api";
import { DriveFolderPickerButton } from "./DriveFolderPicker";
import {
  streamGoogleExportEvents,
  useGoogleExportStatus,
  useSetGoogleDriveFolder,
  useTriggerGoogleExport,
  type GoogleExportProgressEvent,
} from "./api";

type Step = "options" | "progress" | "done" | "error";
type PortfolioChoice = "auto" | "yes" | "no";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function ExportOptionsDialog({
  open,
  onClose,
  integration,
}: {
  open: boolean;
  onClose: () => void;
  integration: GoogleIntegration;
}) {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const triggerExport = useTriggerGoogleExport();
  const setFolder = useSetGoogleDriveFolder();
  const exportStatus = useGoogleExportStatus();

  const [step, setStep] = useState<Step>("options");
  const [dateFrom, setDateFrom] = useState(() => isoDaysAgo(365));
  const [dateTo, setDateTo] = useState(() => isoDaysAgo(0));
  const [portfolioChoice, setPortfolioChoice] = useState<PortfolioChoice>("auto");
  const [includeCharts, setIncludeCharts] = useState(true);
  const [folderError, setFolderError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [progressMessage, setProgressMessage] = useState(() => t("items.integrations.page.exportDialog.inProgress"));
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = () => {
    abortRef.current?.abort();
    setStep("options");
    setSubmitError(null);
    setFolderError(null);
    setResultMessage(null);
  };

  const close = () => {
    reset();
    onClose();
  };

  const onExport = async () => {
    setSubmitError(null);
    try {
      await triggerExport.mutateAsync({
        date_from: dateFrom,
        date_to: dateTo,
        include_portfolio: portfolioChoice === "auto" ? null : portfolioChoice === "yes",
        include_charts: includeCharts,
        // Fetta 3 (PLAN_TAXONOMY_I18N.md): il contenuto scritto nei fogli
        // segue la lingua UI corrente — mai i titoli dei tab (fissi).
        language: i18n.language === "en" ? "en" : "it",
      });
      setStep("progress");
    } catch (error) {
      setSubmitError(friendlyErrorMessage(error, t("items.integrations.page.exportDialog.submitError")));
    }
  };

  useEffect(() => {
    if (step !== "progress") return;
    const controller = new AbortController();
    abortRef.current = controller;

    const handleEvent = (event: GoogleExportProgressEvent) => {
      if (event.stage) setProgressMessage(event.stage);
      if (event.event === "job.completed") {
        setResultMessage(event.message ?? t("items.integrations.page.exportDialog.completed"));
        setStep("done");
      }
      if (event.event === "job.failed") {
        setResultMessage(event.message ?? t("items.integrations.page.exportDialog.failed"));
        setStep("error");
      }
    };

    streamGoogleExportEvents(handleEvent, controller.signal).catch(() => {
      // Fallback: useGoogleExportStatus continua a fare polling (vedi sotto)
      // se lo stream si interrompe.
    });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `t` stabile, non serve nelle dep
  }, [step]);

  // Fallback se il polling di stato segnala terminato prima (o al posto)
  // dello stream SSE.
  useEffect(() => {
    if (step !== "progress" || !exportStatus.data) return;
    if (exportStatus.data.status === "success") {
      setResultMessage(exportStatus.data.message ?? t("items.integrations.page.exportDialog.completed"));
      setStep("done");
    }
    if (exportStatus.data.status === "failed") {
      setResultMessage(exportStatus.data.message ?? t("items.integrations.page.exportDialog.failed"));
      setStep("error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `t` stabile, non serve nelle dep
  }, [exportStatus.data, step]);

  return (
    <Dialog open={open} onClose={close} title={t("items.integrations.page.exportDialog.title")}>
      {step === "options" && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
            <div>
              <p className="text-sm font-medium text-text">{t("items.integrations.page.exportDialog.driveFolder")}</p>
              <p className="text-sm text-text-muted">
                {integration.drive_folder_name ?? t("items.integrations.page.folderRoot")}
              </p>
            </div>
            <DriveFolderPickerButton
              label={t("items.integrations.page.changeFolder")}
              onPicked={(folder) => {
                setFolderError(null);
                setFolder.mutate({ folder_id: folder.id, folder_name: folder.name });
              }}
              onError={setFolderError}
            />
          </div>
          {folderError && (
            <p role="alert" className="text-sm text-danger">
              {folderError}
            </p>
          )}

          <div className="flex gap-3">
            <Input
              type="date"
              label={t("items.integrations.page.exportDialog.dateFrom")}
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
            <Input
              type="date"
              label={t("items.integrations.page.exportDialog.dateTo")}
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>

          <Select
            label={t("items.integrations.page.exportDialog.portfolioSheet")}
            value={portfolioChoice}
            onChange={(e) => setPortfolioChoice(e.target.value as PortfolioChoice)}
          >
            <option value="auto">{t("items.integrations.page.exportDialog.portfolioAuto")}</option>
            <option value="yes">{t("items.integrations.page.exportDialog.portfolioAlways")}</option>
            <option value="no">{t("items.integrations.page.exportDialog.portfolioNever")}</option>
          </Select>

          <label className="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={includeCharts}
              onChange={(e) => setIncludeCharts(e.target.checked)}
              className="h-4 w-4 rounded border-border"
            />
            {t("items.integrations.page.exportDialog.includeCharts")}
          </label>

          {submitError && (
            <p role="alert" className="text-sm text-danger">
              {submitError}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close}>
              {t("common:actions.cancel")}
            </Button>
            <Button onClick={() => void onExport()} loading={triggerExport.isPending}>
              {t("items.integrations.page.export")}
            </Button>
          </div>
        </div>
      )}

      {step === "progress" && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2 text-sm text-text">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            {progressMessage}
          </div>
        </div>
      )}

      {step === "done" && (
        <div className="flex flex-col gap-4">
          <p className="flex items-center gap-2 text-text">
            <Check className="h-5 w-5 text-success" /> {resultMessage}
          </p>
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => window.open(integration.spreadsheet_url, "_blank", "noopener,noreferrer")}
            >
              {t("items.integrations.page.openSpreadsheet")}
            </Button>
            <Button onClick={close}>{t("common:actions.close")}</Button>
          </div>
        </div>
      )}

      {step === "error" && (
        <div className="flex flex-col gap-4">
          <p className="flex items-center gap-2 text-danger">
            <Circle className="h-5 w-5" /> {resultMessage}
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close}>
              {t("common:actions.close")}
            </Button>
            <Button onClick={() => setStep("options")}>{t("common:actions.retry")}</Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
