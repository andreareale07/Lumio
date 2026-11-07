import { useCallback, useEffect, useId, useState } from "react";
import { Database, Link2Off, PlugZap, RefreshCwOff, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { BottomSheet } from "../../../components/ui/BottomSheet";
import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { useIsDesktop } from "../../../lib/useIsDesktop";
import type { BankConnection } from "../../../types/api";

interface Props {
  connection: BankConnection | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: (deleteData: boolean) => void;
}

function ImpactRow({ icon, danger = false, children }: { icon: ReactNode; danger?: boolean; children: ReactNode }) {
  return (
    <li className={`flex min-h-9 items-start gap-3 py-1.5 text-sm ${danger ? "text-danger" : "text-text-muted"}`}>
      <span className="mt-0.5 shrink-0" aria-hidden="true">
        {icon}
      </span>
      <span>{children}</span>
    </li>
  );
}

/** Conferma dello scollegamento con il riepilogo di cio' che succede: foglio dal
 * basso su smartphone, finestra su desktop. "Annulla" e "Scollega" hanno lo
 * stesso peso visivo. Di default i movimenti importati restano; una casella
 * esplicita permette di eliminarli (solo quelli importati da questa banca). */
export function DisconnectSheet({ connection, loading, error, onClose, onConfirm }: Props) {
  const { t } = useTranslation(["settings", "common"]);
  const isDesktop = useIsDesktop();
  const [deleteData, setDeleteData] = useState(false);
  const checkboxId = useId();
  const open = connection !== null;

  // Ogni apertura riparte dallo stato prudente: i dati restano.
  useEffect(() => {
    if (open) setDeleteData(false);
  }, [open]);

  const close = useCallback(() => onClose(), [onClose]);
  if (!connection) return null;

  const base = "items.bankConnections.page.connection.disconnectDialog";
  const imported = connection.accounts.reduce((sum, account) => sum + account.transactions_imported, 0);
  const title = t(`settings:${base}.title`, { bank: connection.aspsp_name });

  const content = (
    <div className="flex flex-col gap-3">
      <ul className="divide-y divide-border">
        <ImpactRow icon={<PlugZap className="h-4 w-4" />}>{t(`settings:${base}.impact.revoke`)}</ImpactRow>
        <ImpactRow icon={<RefreshCwOff className="h-4 w-4" />}>{t(`settings:${base}.impact.stopSync`)}</ImpactRow>
        <ImpactRow icon={deleteData ? <Trash2 className="h-4 w-4" /> : <Database className="h-4 w-4" />} danger={deleteData}>
          {deleteData
            ? t(`settings:${base}.impact.delete`, { count: imported })
            : t(`settings:${base}.impact.keep`, { count: imported })}
        </ImpactRow>
        <ImpactRow icon={<Link2Off className="h-4 w-4" />}>{t(`settings:${base}.impact.mappings`)}</ImpactRow>
      </ul>

      <div className="rounded-lg border border-border p-3">
        <label htmlFor={checkboxId} className="flex min-h-11 cursor-pointer items-start gap-3 text-sm text-text">
          <input
            id={checkboxId}
            type="checkbox"
            checked={deleteData}
            onChange={(event) => setDeleteData(event.target.checked)}
            className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--color-danger,#dc2626)]"
          />
          <span>{t(`settings:${base}.deleteLabel`)}</span>
        </label>
        {deleteData && (
          <p role="note" className="mt-1 text-sm text-danger">
            {t(`settings:${base}.deleteWarning`)}
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );

  const footer = (
    <>
      <Button variant="secondary" onClick={close} className="flex-1 sm:flex-none">
        {t("common:actions.cancel")}
      </Button>
      <Button
        variant="danger"
        loading={loading}
        onClick={() => onConfirm(deleteData)}
        className="flex-1 sm:flex-none"
      >
        {deleteData ? t(`settings:${base}.confirmDelete`) : t("settings:items.bankConnections.page.connection.disconnect")}
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
