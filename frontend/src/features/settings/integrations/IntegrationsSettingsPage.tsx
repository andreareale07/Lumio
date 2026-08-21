import { useEffect, useState } from "react";
import { ExternalLink, FileSpreadsheet } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Dialog } from "../../../components/ui/Dialog";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { JobRunStatus } from "../../../components/ui/JobRunStatus";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import { formatDateTime } from "../../../lib/format";
import { DriveFolderPickerButton } from "./DriveFolderPicker";
import { ExportOptionsDialog } from "./ExportOptionsDialog";
import {
  useConnectGoogle,
  useDisconnectGoogle,
  useGoogleExportStatus,
  useGoogleIntegration,
  useSetGoogleDriveFolder,
} from "./api";

export function IntegrationsSettingsPage() {
  const { t } = useTranslation(["settings", "common"]);
  const { data: integration, isLoading, isError, refetch } = useGoogleIntegration();
  const connectGoogle = useConnectGoogle();
  const disconnectGoogle = useDisconnectGoogle();
  const setFolder = useSetGoogleDriveFolder();
  const exportStatus = useGoogleExportStatus();
  const [searchParams, setSearchParams] = useSearchParams();

  const [showFolderPrompt, setShowFolderPrompt] = useState(
    () => searchParams.get("connected") === "1" && searchParams.get("step") === "choose-folder",
  );
  const [googleErrorCode] = useState(() => searchParams.get("google_error"));
  const [connectError, setConnectError] = useState<string | null>(null);
  const [folderError, setFolderError] = useState<string | null>(null);
  const [disconnectConfirmOpen, setDisconnectConfirmOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);

  useEffect(() => {
    if (searchParams.has("connected") || searchParams.has("google_error")) {
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const onConnect = async () => {
    setConnectError(null);
    try {
      const { authorize_url } = await connectGoogle.mutateAsync();
      window.location.assign(authorize_url);
    } catch {
      setConnectError(t("items.integrations.page.connectError"));
    }
  };

  const googleErrorMessage = googleErrorCode
    ? (t(`items.integrations.page.errorCodes.${googleErrorCode}`, { defaultValue: "" }) as string) ||
      t("items.integrations.page.errorGeneric")
    : null;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <h1 className="text-lg font-semibold text-text">{t("items.integrations.label")}</h1>
      <p className="text-sm text-text-muted">{t("items.integrations.pageDescription")}</p>

      {isLoading && <SkeletonRows rows={3} />}
      {isError && <ErrorState message={t("items.integrations.page.loadError")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && !integration && (
        <>
          {googleErrorMessage && (
            <p role="alert" className="text-sm text-danger">
              {googleErrorMessage}
            </p>
          )}
          <EmptyState
            icon={FileSpreadsheet}
            title={t("items.integrations.page.empty.title")}
            description={t("items.integrations.page.empty.description")}
            action={
              <Button onClick={() => void onConnect()} loading={connectGoogle.isPending}>
                {t("items.integrations.page.connect")}
              </Button>
            }
          />
          {connectError && (
            <p role="alert" className="text-sm text-danger">
              {connectError}
            </p>
          )}
          <SetupGuide />
        </>
      )}

      {!isLoading && !isError && integration && (
        <>
          {showFolderPrompt && (
            <Card className="flex flex-wrap items-center justify-between gap-3 border-primary/40">
              <div>
                <p className="font-medium text-text">{t("items.integrations.page.folderPrompt.title")}</p>
                <p className="text-sm text-text-muted">{t("items.integrations.page.folderPrompt.description")}</p>
              </div>
              <div className="flex gap-2">
                <DriveFolderPickerButton
                  label={t("items.integrations.page.folderPrompt.chooseFolder")}
                  onPicked={(folder) => {
                    setFolderError(null);
                    setFolder.mutate(
                      { folder_id: folder.id, folder_name: folder.name },
                      { onSuccess: () => setShowFolderPrompt(false) },
                    );
                  }}
                  onError={setFolderError}
                />
                <Button variant="ghost" size="sm" onClick={() => setShowFolderPrompt(false)}>
                  {t("items.integrations.page.folderPrompt.hide")}
                </Button>
              </div>
            </Card>
          )}

          <Card className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <FileSpreadsheet className="h-8 w-8 text-text-muted" aria-hidden="true" />
                <div>
                  <p className="font-medium text-text">{t("items.integrations.page.connected")}</p>
                  <p className="text-sm text-text-muted">{integration.google_account_email}</p>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-1 rounded-lg border border-border p-3 text-sm">
              <a
                href={integration.spreadsheet_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 font-medium text-primary hover:underline"
              >
                {t("items.integrations.page.openSpreadsheet")} <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-text-muted">
                  {t("items.integrations.page.folder", {
                    name: integration.drive_folder_name ?? t("items.integrations.page.folderRoot"),
                  })}
                </p>
                <DriveFolderPickerButton
                  label={t("items.integrations.page.changeFolder")}
                  variant="ghost"
                  onPicked={(folder) => {
                    setFolderError(null);
                    setFolder.mutate({ folder_id: folder.id, folder_name: folder.name });
                  }}
                  onError={setFolderError}
                />
              </div>
              <p className="text-text-muted">
                {t("items.integrations.page.lastExport", {
                  value: integration.last_exported_at
                    ? formatDateTime(integration.last_exported_at)
                    : t("items.integrations.page.lastExportNever"),
                })}
              </p>
            </div>
            {folderError && (
              <p role="alert" className="text-sm text-danger">
                {folderError}
              </p>
            )}

            <JobRunStatus run={exportStatus.data} />

            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDisconnectConfirmOpen(true)}>
                {t("items.integrations.page.disconnect")}
              </Button>
              <Button onClick={() => setExportDialogOpen(true)}>{t("items.integrations.page.export")}</Button>
            </div>
          </Card>

          <ExportOptionsDialog open={exportDialogOpen} onClose={() => setExportDialogOpen(false)} integration={integration} />

          <Dialog
            open={disconnectConfirmOpen}
            onClose={() => setDisconnectConfirmOpen(false)}
            title={t("items.integrations.page.disconnectDialog.title")}
          >
            <p className="text-sm text-text-muted">{t("items.integrations.page.disconnectDialog.body")}</p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDisconnectConfirmOpen(false)}>
                {t("common:actions.cancel")}
              </Button>
              <Button
                variant="danger"
                loading={disconnectGoogle.isPending}
                onClick={async () => {
                  await disconnectGoogle.mutateAsync();
                  setDisconnectConfirmOpen(false);
                }}
              >
                {t("items.integrations.page.disconnect")}
              </Button>
            </div>
          </Dialog>
        </>
      )}
    </div>
  );
}

/** Guida completa passo-passo (non solo un riepilogo): l'utente ha chiesto
 * esplicitamente di averla "direttamente nella pagina", non solo in chat —
 * un self-hoster alle prime armi deve poter seguire tutto qui, senza uscire
 * dall'app. L'URI di redirect e' calcolato da `window.location.origin`
 * invece che scritto a mano: deve combaciare ESATTAMENTE (Google non
 * accetta match parziali) con quello su cui gira DAVVERO questa istanza,
 * che puo' non essere "localhost:5173" (NAS, IP di rete locale, dominio). */
function SetupGuide() {
  const { t } = useTranslation("settings");
  const redirectUri = `${window.location.origin}/api/v1/integrations/google/callback`;
  const [copied, setCopied] = useState(false);

  const copyRedirectUri = async () => {
    try {
      await navigator.clipboard.writeText(redirectUri);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard non disponibile (es. contesto non sicuro): l'utente copia a mano dal riquadro.
    }
  };

  // Ogni passo mischia enfasi (<strong>/<em>) e nomi letterali (<code>,
  // invariati fra le lingue) dentro la stessa frase: <Trans> con i
  // component mapping a livello di TAG NAME (non per occorrenza) risolve
  // ripetizioni multiple dello stesso tag nella stessa chiave — vedi
  // "enableApis" (3x <strong>) o "pasteValues" (5x <code>).
  const stepComponents = {
    strong: <strong className="text-text" />,
    em: <em />,
    code: <code className="rounded bg-surface-hover px-1 py-0.5 font-mono text-xs" />,
  };

  return (
    <Card className="flex flex-col gap-3 text-sm">
      <div>
        <p className="font-medium text-text">{t("items.integrations.page.setupGuide.intro.title")}</p>
        <p className="text-text-muted">{t("items.integrations.page.setupGuide.intro.description")}</p>
      </div>

      <ol className="list-decimal space-y-3 pl-5 text-text-muted">
        <li>
          <Trans t={t} i18nKey="items.integrations.page.setupGuide.steps.createProject" components={stepComponents} />
        </li>
        <li>
          <Trans t={t} i18nKey="items.integrations.page.setupGuide.steps.enableApis" components={stepComponents} />
        </li>
        <li>
          <Trans t={t} i18nKey="items.integrations.page.setupGuide.steps.consentScreen" components={stepComponents} />
        </li>
        <li>
          <Trans
            t={t}
            i18nKey="items.integrations.page.setupGuide.steps.createCredentialsIntro"
            components={stepComponents}
          />
          <div className="mt-1.5 flex items-center gap-2 rounded-md border border-border bg-surface-hover px-2 py-1.5 font-mono text-xs text-text">
            <code className="flex-1 break-all">{redirectUri}</code>
            <button
              type="button"
              onClick={() => void copyRedirectUri()}
              className="shrink-0 font-sans font-medium text-primary hover:underline"
            >
              {copied ? t("items.integrations.page.setupGuide.copied") : t("items.integrations.page.setupGuide.copy")}
            </button>
          </div>
          <span className="mt-1 block">
            <Trans
              t={t}
              i18nKey="items.integrations.page.setupGuide.steps.createCredentialsOutro"
              components={stepComponents}
            />
          </span>
        </li>
        <li>
          <Trans t={t} i18nKey="items.integrations.page.setupGuide.steps.pickerKey" components={stepComponents} />
        </li>
        <li>
          <Trans t={t} i18nKey="items.integrations.page.setupGuide.steps.pasteValues" components={stepComponents} />
        </li>
      </ol>

      <a
        href="https://console.cloud.google.com/"
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1.5 font-medium text-primary hover:underline"
      >
        {t("items.integrations.page.setupGuide.openConsole")} <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
      </a>
    </Card>
  );
}
