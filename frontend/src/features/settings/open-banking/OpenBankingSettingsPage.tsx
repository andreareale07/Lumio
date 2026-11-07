import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Download, Landmark, Plus } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { usePageToolbar } from "../../../components/layout/PageToolbarContext";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Dialog } from "../../../components/ui/Dialog";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import type { BankConnection, BankConnectionAccount } from "../../../types/api";
import {
  useBankConnections,
  useDeleteCredentials,
  useDisconnectBank,
  useOpenBankingStatus,
  useResyncHistory,
  useSyncConnection,
  useUpdateBankAccount,
} from "./api";
import { needsRenewal } from "./bankStatus";
import { AccountDetailsSheet } from "./AccountDetailsSheet";
import { ConnectBankDialog } from "./ConnectBankDialog";
import type { BankChoice } from "./ConnectBankDialog";
import { ConnectionCard } from "./ConnectionCard";
import type { SyncOutcome } from "./ConnectionStatusLine";
import { MapAccountDialog } from "./MapAccountDialog";
import { DisconnectSheet } from "./DisconnectSheet";
import { downloadCertificate } from "./downloadCertificate";
import { SetupWizard } from "./SetupWizard";

const SYNC_GIVE_UP_MS = 120_000;

interface SyncSnapshot {
  lastSyncAt: string | null;
  lastError: string | null;
  imported: number;
  seenRunning: boolean;
}

const importedTotal = (connection: BankConnection) =>
  connection.accounts.reduce((sum, account) => sum + account.transactions_imported, 0);

/** Pagina `/settings/bank-connections` (Open Banking, opzionale: con
 * `OPEN_BANKING_ENABLED=false` non esiste). Tre stati: configurazione guidata
 * (credenziali personali dell'utente), elenco banche collegate, e il flusso
 * "Collega una banca" che porta l'utente sul sito della banca. */
export function OpenBankingSettingsPage() {
  const { t } = useTranslation(["settings", "common"]);
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const status = useOpenBankingStatus();

  const [snapshots, setSnapshots] = useState<Record<string, SyncSnapshot>>({});
  const [outcomes, setOutcomes] = useState<Record<string, SyncOutcome>>({});
  const [syncError, setSyncError] = useState<string | null>(null);
  const configured = status.data?.credential?.configured === true;
  const snapshotsRef = useRef(snapshots);
  snapshotsRef.current = snapshots;
  const connections = useBankConnections({ pollWhile: () => Object.keys(snapshotsRef.current).length > 0 });
  const connectionList = connections.data ?? [];

  const syncConnection = useSyncConnection();
  const resyncHistory = useResyncHistory();
  const disconnectBank = useDisconnectBank();
  const deleteCredentials = useDeleteCredentials();
  const updateAccount = useUpdateBankAccount();

  const [connectOpen, setConnectOpen] = useState(false);
  const [renewBank, setRenewBank] = useState<BankChoice | null>(null);
  const [mapping, setMapping] = useState<{ connection: BankConnection; account: BankConnectionAccount } | null>(null);
  // Callback stabili per i dialog con campi: vedi il commento in ConnectBankDialog.
  const closeConnect = useCallback(() => setConnectOpen(false), []);
  const closeRenew = useCallback(() => setRenewBank(null), []);
  const closeMapping = useCallback(() => setMapping(null), []);
  const [details, setDetails] = useState<{ connectionId: string; accountId: string } | null>(null);
  const [resyncError, setResyncError] = useState<string | null>(null);
  const closeDetails = useCallback(() => {
    setDetails(null);
    setResyncError(null);
  }, []);
  // Elenco compatto: ogni banca e' una riga espandibile. Si aprono da sole la
  // banca appena collegata, quella che richiede un rinnovo, una in sincronizzazione
  // e l'unica banca quando ce n'e' una sola.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const seenIds = useRef<Set<string>>(new Set());
  const toggleExpanded = (id: string) =>
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const [disconnecting, setDisconnecting] = useState<BankConnection | null>(null);
  const [disconnectError, setDisconnectError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const closeDisconnect = useCallback(() => {
    setDisconnecting(null);
    setDisconnectError(null);
  }, []);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [accountPending, setAccountPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Esito del ritorno dalla banca (parametri dell'URL, poi ripuliti).
  const [returned] = useState(() => ({
    connected: searchParams.get("connected"),
    error: searchParams.get("error"),
  }));
  useEffect(() => {
    if (searchParams.has("connected") || searchParams.has("error")) setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const data = connections.data;
    if (!data) return;
    const toOpen = data
      .filter((connection) => !seenIds.current.has(connection.id))
      .filter(
        (connection) =>
          data.length === 1 ||
          needsRenewal(connection) ||
          connection.sync_running ||
          connection.id === returned.connected,
      )
      .map((connection) => connection.id);
    data.forEach((connection) => seenIds.current.add(connection.id));
    if (toOpen.length > 0) setExpanded((previous) => new Set([...previous, ...toOpen]));
  }, [connections.data, returned.connected]);

  // Chiude il ciclo di una sync manuale: la pagina ricava l'esito confrontando lo stato prima/dopo.
  useEffect(() => {
    const data = connections.data;
    if (!data || Object.keys(snapshotsRef.current).length === 0) return;
    let changed = false;
    const next = { ...snapshotsRef.current };
    const finished: Record<string, SyncOutcome> = {};
    for (const connection of data) {
      const snapshot = next[connection.id];
      if (!snapshot) continue;
      if (connection.sync_running && !snapshot.seenRunning) {
        next[connection.id] = { ...snapshot, seenRunning: true };
        changed = true;
        continue;
      }
      const done =
        !connection.sync_running &&
        (snapshot.seenRunning ||
          connection.last_sync_at !== snapshot.lastSyncAt ||
          connection.last_error !== snapshot.lastError);
      if (done) {
        finished[connection.id] = {
          imported: Math.max(importedTotal(connection) - snapshot.imported, 0),
          error: connection.last_error,
        };
        delete next[connection.id];
        changed = true;
      }
    }
    if (!changed) return;
    setSnapshots(next);
    if (Object.keys(finished).length > 0) {
      setOutcomes((previous) => ({ ...previous, ...finished }));
      if (Object.values(finished).some((outcome) => outcome.imported > 0)) {
        // Nuovi movimenti: le altre pagine (movimenti, conti, analisi) vanno riallineate.
        void queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "open-banking" });
      }
    }
  }, [connections.data, queryClient]);

  // Se il worker non risponde, dopo un po' si smette di aspettare invece di restare "in corso" per sempre.
  useEffect(() => {
    if (Object.keys(snapshots).length === 0) return undefined;
    const timer = setTimeout(() => setSnapshots({}), SYNC_GIVE_UP_MS);
    return () => clearTimeout(timer);
  }, [snapshots]);

  const trackSync = (connection: BankConnection) =>
    setSnapshots((previous) => ({
      ...previous,
      [connection.id]: {
        lastSyncAt: connection.last_sync_at,
        lastError: connection.last_error,
        imported: importedTotal(connection),
        seenRunning: false,
      },
    }));

  const startSync = async (connection: BankConnection) => {
    setSyncError(null);
    setOutcomes((previous) => Object.fromEntries(Object.entries(previous).filter(([id]) => id !== connection.id)));
    try {
      await syncConnection.mutateAsync(connection.id);
      trackSync(connection);
    } catch (error) {
      setSyncError(friendlyErrorMessage(error, t("settings:items.bankConnections.page.connection.syncStartError")));
    }
  };

  const startResync = async (connection: BankConnection, account: BankConnectionAccount) => {
    setResyncError(null);
    try {
      await resyncHistory.mutateAsync({ connectionId: connection.id, accountId: account.id });
      setOutcomes((previous) => Object.fromEntries(Object.entries(previous).filter(([id]) => id !== connection.id)));
      trackSync(connection);
      closeDetails();
      // Il cursore e' stato azzerato (i movimenti eliminati a mano tornano): riallinea le altre pagine.
      void queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "open-banking" });
    } catch (error) {
      setResyncError(friendlyErrorMessage(error, t("settings:items.bankConnections.page.diagnostics.resync.error")));
    }
  };

  const toggleAccount = async (connection: BankConnection, account: BankConnectionAccount, enabled: boolean) => {
    setActionError(null);
    setAccountPending(account.id);
    try {
      await updateAccount.mutateAsync({ connectionId: connection.id, accountId: account.id, update: { enabled } });
    } catch (error) {
      setActionError(friendlyErrorMessage(error, t("settings:items.bankConnections.page.connection.toggleError")));
    } finally {
      setAccountPending(null);
    }
  };

  const connectButton = (
    <Button size="sm" onClick={() => setConnectOpen(true)} disabled={!configured}>
      <Plus className="h-4 w-4" aria-hidden="true" /> {t("settings:items.bankConnections.page.connectButton")}
    </Button>
  );
  const toolbarPortal = usePageToolbar(configured ? connectButton : null);

  const isLoading = status.isLoading || (configured && connections.isLoading);
  const hasConnections = connectionList.length > 0;
  const returnedError = returned.error
    ? (t(`settings:items.bankConnections.page.errorCodes.${returned.error}`, { defaultValue: "" }) as string) ||
      t("settings:items.bankConnections.page.errorCodes.generic")
    : null;
  const credential = status.data?.credential ?? null;
  const detailsConnection = connectionList.find((connection) => connection.id === details?.connectionId) ?? null;
  const detailsAccount = detailsConnection?.accounts.find((account) => account.id === details?.accountId) ?? null;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      {toolbarPortal}
      <div>
        <h1 className="text-lg font-semibold text-text">{t("settings:items.bankConnections.label")}</h1>
        <p className="text-sm text-text-muted">{t("settings:items.bankConnections.pageDescription")}</p>
      </div>

      {configured && hasConnections && (
        <div className="md:hidden">
          <Button className="w-full" onClick={() => setConnectOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" /> {t("settings:items.bankConnections.page.connectButton")}
          </Button>
        </div>
      )}

      {returned.connected && (
        <p role="status" className="flex items-start gap-2 rounded-lg border border-success/40 bg-success-bg p-3 text-sm text-success">
          <Check className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {t("settings:items.bankConnections.page.connectedBanner")}
        </p>
      )}
      {returnedError && (
        <p role="alert" className="rounded-lg border border-danger/40 bg-danger-bg p-3 text-sm text-danger">
          {returnedError}
        </p>
      )}

      {isLoading && <SkeletonRows rows={3} />}
      {status.isError && (
        <ErrorState message={t("settings:items.bankConnections.page.loadError")} onRetry={() => void status.refetch()} />
      )}

      {!isLoading && !status.isError && status.data && (
        <>
          {!status.data.redirect_uri_configured && (
            <div role="alert" className="rounded-lg border border-warning/40 bg-warning-bg p-3 text-sm text-warning">
              <p className="font-medium">{t("settings:items.bankConnections.page.redirectMissing.title")}</p>
              <p>{t("settings:items.bankConnections.page.redirectMissing.body")}</p>
            </div>
          )}

          {!configured && <SetupWizard status={status.data} />}

          {configured && connections.isError && (
            <ErrorState
              message={t("settings:items.bankConnections.page.loadError")}
              onRetry={() => void connections.refetch()}
            />
          )}

          {configured && !connections.isError && !hasConnections && (
            <EmptyState
              icon={Landmark}
              title={t("settings:items.bankConnections.page.empty.title")}
              description={t("settings:items.bankConnections.page.empty.description")}
              action={
                <Button onClick={() => setConnectOpen(true)}>
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  {t("settings:items.bankConnections.page.connectButton")}
                </Button>
              }
            />
          )}

          {syncError && (
            <p role="alert" className="text-sm text-danger">
              {syncError}
            </p>
          )}
          {notice && (
            <p role="status" className="flex items-start gap-2 rounded-lg bg-surface-hover p-3 text-sm text-text">
              <Check className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {notice}
            </p>
          )}
          {actionError && (
            <p role="alert" className="text-sm text-danger">
              {actionError}
            </p>
          )}

          {configured && hasConnections && (
            <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
              {connectionList.map((connection) => (
              <ConnectionCard
                key={connection.id}
                connection={connection}
                expanded={expanded.has(connection.id)}
                onToggle={() => toggleExpanded(connection.id)}
                syncing={connection.sync_running || connection.id in snapshots}
                outcome={outcomes[connection.id] ?? null}
                accountPending={accountPending}
                onSync={() => void startSync(connection)}
                onRenew={() =>
                  setRenewBank({ name: connection.aspsp_name, country: connection.aspsp_country })
                }
                onDisconnect={() => setDisconnecting(connection)}
                onImportAccount={(account) => setMapping({ connection, account })}
                onToggleAccount={(account, enabled) => void toggleAccount(connection, account, enabled)}
                onAccountDetails={(account) => setDetails({ connectionId: connection.id, accountId: account.id })}
              />
              ))}
            </div>
          )}

          {configured && credential && (
            <Card className="flex flex-col gap-3 text-sm">
              <div>
                <h2 className="font-medium text-text">{t("settings:items.bankConnections.page.credentials.title")}</h2>
                <p className="text-text-muted">
                  {t("settings:items.bankConnections.page.credentials.applicationId", {
                    id: credential.application_id,
                  })}
                </p>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:flex sm:justify-between">
                <Button variant="secondary" onClick={() => downloadCertificate(credential.certificate_pem)}>
                  <Download className="h-4 w-4" aria-hidden="true" />
                  {t("settings:items.bankConnections.page.credentials.download")}
                </Button>
                <Button variant="ghost" className="text-danger hover:bg-danger-bg" onClick={() => setDeleteOpen(true)}>
                  {t("settings:items.bankConnections.page.credentials.delete")}
                </Button>
              </div>
            </Card>
          )}

          <ul className="flex flex-col gap-1.5 rounded-lg bg-surface-hover p-3 text-xs text-text-muted">
            <li>{t("settings:items.bankConnections.page.privacy.readOnly")}</li>
            <li>{t("settings:items.bankConnections.page.privacy.local")}</li>
            <li>{t("settings:items.bankConnections.page.privacy.personalUse")}</li>
          </ul>
        </>
      )}

      <AccountDetailsSheet
        account={detailsAccount}
        loading={resyncHistory.isPending}
        error={resyncError}
        onClose={closeDetails}
        onResync={() => detailsConnection && detailsAccount && void startResync(detailsConnection, detailsAccount)}
      />
      <ConnectBankDialog open={connectOpen} onClose={closeConnect} />
      {renewBank && (
        <ConnectBankDialog open onClose={closeRenew} initialBank={renewBank} />
      )}
      {mapping && (
        <MapAccountDialog connectionId={mapping.connection.id} account={mapping.account} onClose={closeMapping} />
      )}

      <DisconnectSheet
        connection={disconnecting}
        loading={disconnectBank.isPending}
        error={disconnectError}
        onClose={closeDisconnect}
        onConfirm={async (deleteData) => {
          if (!disconnecting) return;
          setDisconnectError(null);
          try {
            const result = await disconnectBank.mutateAsync({ connectionId: disconnecting.id, deleteData });
            const base = "settings:items.bankConnections.page.connection";
            const bank = disconnecting.aspsp_name;
            setNotice(
              [
                result.deleted_transactions > 0
                  ? t(`${base}.disconnectedDeleted`, { bank, count: result.deleted_transactions })
                  : t(`${base}.disconnected`, { bank }),
                result.revoked_at_bank ? null : t(`${base}.notRevoked`),
              ]
                .filter(Boolean)
                .join(" "),
            );
            setDisconnecting(null);
          } catch (error) {
            // Resta aperto il foglio: l'utente vede il motivo (es. importazione in corso) e puo' riprovare.
            setDisconnectError(
              friendlyErrorMessage(error, t("settings:items.bankConnections.page.connection.disconnectError")),
            );
          }
        }}
      />

      <Dialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title={t("settings:items.bankConnections.page.credentials.deleteDialog.title")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteOpen(false)} className="flex-1 sm:flex-none">
              {t("common:actions.cancel")}
            </Button>
            <Button
              variant="danger"
              className="flex-1 sm:flex-none"
              loading={deleteCredentials.isPending}
              onClick={async () => {
                try {
                  await deleteCredentials.mutateAsync();
                } catch (error) {
                  setActionError(
                    friendlyErrorMessage(error, t("settings:items.bankConnections.page.credentials.deleteError")),
                  );
                }
                setDeleteOpen(false);
              }}
            >
              {t("settings:items.bankConnections.page.credentials.deleteDialog.confirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-text-muted">{t("settings:items.bankConnections.page.credentials.deleteDialog.body")}</p>
      </Dialog>
    </div>
  );
}
