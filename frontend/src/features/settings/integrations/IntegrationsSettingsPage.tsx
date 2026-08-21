import { useEffect, useState } from "react";
import { ExternalLink, FileSpreadsheet } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

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

const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  missing_code: "Google non ha restituito un codice di autorizzazione. Riprova.",
  invalid_state: "La richiesta di connessione non è valida o è scaduta. Riprova.",
  connection_failed: "Non è stato possibile completare la connessione con Google. Riprova.",
};

export function IntegrationsSettingsPage() {
  const { t } = useTranslation("settings");
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
      setConnectError("Non è stato possibile avviare la connessione con Google.");
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <h1 className="text-lg font-semibold text-text">{t("items.integrations.label")}</h1>
      <p className="text-sm text-text-muted">
        Google Sheets è un'integrazione opzionale: esporta i tuoi dati finanziari in un foglio Google, sempre
        aggiornabile su richiesta. Disattivarla non ha alcun impatto sul resto di Lumio.
      </p>

      {isLoading && <SkeletonRows rows={3} />}
      {isError && <ErrorState message="Non siamo riusciti a caricare lo stato dell'integrazione." onRetry={() => void refetch()} />}

      {!isLoading && !isError && !integration && (
        <>
          {googleErrorCode && (
            <p role="alert" className="text-sm text-danger">
              {GOOGLE_ERROR_MESSAGES[googleErrorCode] ?? "Si è verificato un errore con Google."}
            </p>
          )}
          <EmptyState
            icon={FileSpreadsheet}
            title="Google Sheets"
            description="Esporta i tuoi dati finanziari in un foglio Google, con grafici e riepiloghi pronti."
            action={
              <Button onClick={() => void onConnect()} loading={connectGoogle.isPending}>
                Connetti
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
                <p className="font-medium text-text">Dove vuoi salvare il file?</p>
                <p className="text-sm text-text-muted">
                  Il file è stato creato nella root del tuo Google Drive ("Il mio Drive"). Puoi spostarlo in una
                  cartella specifica, oppure confermare che va bene lì dov'è.
                </p>
              </div>
              <div className="flex gap-2">
                <DriveFolderPickerButton
                  label="Scegli cartella"
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
                  Nascondi
                </Button>
              </div>
            </Card>
          )}

          <Card className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <FileSpreadsheet className="h-8 w-8 text-text-muted" aria-hidden="true" />
                <div>
                  <p className="font-medium text-text">Connesso ✓</p>
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
                Apri lo spreadsheet <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-text-muted">Cartella: {integration.drive_folder_name ?? "Il mio Drive (root)"}</p>
                <DriveFolderPickerButton
                  label="Cambia cartella"
                  variant="ghost"
                  onPicked={(folder) => {
                    setFolderError(null);
                    setFolder.mutate({ folder_id: folder.id, folder_name: folder.name });
                  }}
                  onError={setFolderError}
                />
              </div>
              <p className="text-text-muted">
                Ultimo export:{" "}
                {integration.last_exported_at ? formatDateTime(integration.last_exported_at) : "mai eseguito"}
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
                Disconnetti
              </Button>
              <Button onClick={() => setExportDialogOpen(true)}>Esporta</Button>
            </div>
          </Card>

          <ExportOptionsDialog open={exportDialogOpen} onClose={() => setExportDialogOpen(false)} integration={integration} />

          <Dialog open={disconnectConfirmOpen} onClose={() => setDisconnectConfirmOpen(false)} title="Disconnettere Google?">
            <p className="text-sm text-text-muted">
              Lumio non avrà più accesso al tuo account Google. Lo spreadsheet resterà su Google Drive, ma non verrà
              più aggiornato automaticamente finché non ti riconnetti.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDisconnectConfirmOpen(false)}>
                Annulla
              </Button>
              <Button
                variant="danger"
                loading={disconnectGoogle.isPending}
                onClick={async () => {
                  await disconnectGoogle.mutateAsync();
                  setDisconnectConfirmOpen(false);
                }}
              >
                Disconnetti
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

  return (
    <Card className="flex flex-col gap-3 text-sm">
      <div>
        <p className="font-medium text-text">Prima di connetterti: serve un progetto Google Cloud</p>
        <p className="text-text-muted">
          Lumio è self-hosted: a differenza di un servizio con un unico dominio, non può includere credenziali
          Google già pronte per l'uso (Google richiede un indirizzo di ritorno registrato in anticipo, diverso per
          ogni installazione). Chi gestisce questa istanza crea il proprio progetto — gratuito, una tantum, circa
          10 minuti — esattamente come già fatto per un eventuale provider AI o market data.
        </p>
      </div>

      <ol className="list-decimal space-y-3 pl-5 text-text-muted">
        <li>
          <strong className="text-text">Crea il progetto.</strong> In alto accanto al logo "Google Cloud", apri il
          selettore progetto → <em>Nuovo progetto</em>. Un nome qualsiasi va bene (es. "lumio-personale") →{" "}
          <em>Crea</em>, poi selezionalo come progetto attivo.
        </li>
        <li>
          <strong className="text-text">Abilita le API.</strong> Menu ☰ → <em>API e servizi → Libreria</em>. Cerca
          e abilita <strong className="text-text">Google Sheets API</strong>,{" "}
          <strong className="text-text">Google Drive API</strong> e{" "}
          <strong className="text-text">Google Picker API</strong> (tutte e tre: la Picker API va abilitata a parte,
          non basta Drive — altrimenti non comparirà nell'elenco quando limiti la chiave al passo 5).
        </li>
        <li>
          <strong className="text-text">Configura la schermata di consenso OAuth.</strong> Menu ☰ →{" "}
          <em>API e servizi → Schermata consenso OAuth</em>. Tipo utente <em>Esterno</em>. Nella sezione "Utenti di
          test" aggiungi il tuo indirizzo Gmail: resti così in modalità "Testing", senza bisogno della revisione di
          Google — perfetto per uso personale.
        </li>
        <li>
          <strong className="text-text">Crea le credenziali OAuth.</strong>{" "}
          <em>API e servizi → Credenziali → Crea credenziali → ID client OAuth</em>, tipo{" "}
          <em>Applicazione web</em>. Nell'URI di reindirizzamento autorizzati incolla esattamente:
          <div className="mt-1.5 flex items-center gap-2 rounded-md border border-border bg-surface-hover px-2 py-1.5 font-mono text-xs text-text">
            <code className="flex-1 break-all">{redirectUri}</code>
            <button
              type="button"
              onClick={() => void copyRedirectUri()}
              className="shrink-0 font-sans font-medium text-primary hover:underline"
            >
              {copied ? "Copiato ✓" : "Copia"}
            </button>
          </div>
          <span className="mt-1 block">
            Crea, poi copia <strong className="text-text">ID client</strong> e{" "}
            <strong className="text-text">Secret client</strong>.
          </span>
        </li>
        <li>
          <strong className="text-text">Crea la chiave per il Picker</strong> (selezione cartella Drive). Sempre in{" "}
          <em>Credenziali → Crea credenziali → Chiave API</em>, poi limitala (Modifica → Restrizioni API) a{" "}
          <strong className="text-text">Google Picker API</strong> soltanto.
        </li>
        <li>
          <strong className="text-text">Incolla i 4 valori</strong> (client ID, client secret, l'URI sopra, la
          chiave Picker) nel file <code>.env</code> di questa istanza — variabili <code>GOOGLE_CLIENT_ID</code>,{" "}
          <code>GOOGLE_CLIENT_SECRET</code>, <code>GOOGLE_REDIRECT_URI</code>, <code>GOOGLE_PICKER_API_KEY</code> (e{" "}
          <code>VITE_GOOGLE_PICKER_API_KEY</code> per il frontend) — poi riavvia i container Docker.
        </li>
      </ol>

      <a
        href="https://console.cloud.google.com/"
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1.5 font-medium text-primary hover:underline"
      >
        Apri Google Cloud Console <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
      </a>
    </Card>
  );
}
