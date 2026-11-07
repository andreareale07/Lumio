import { AlertTriangle, ChevronRight, CircleCheck, Loader2, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { formatDateTime } from "../../../lib/format";
import type { BankConnection } from "../../../types/api";
import { statusKeyOf } from "./bankStatus";

export interface SyncOutcome {
  imported: number;
  error: string | null;
}

interface Props {
  connection: BankConnection;
  syncing: boolean;
  outcome: SyncOutcome | null;
  canSync: boolean;
  onRenew: () => void;
  onRetry: () => void;
}

type Tone = "neutral" | "success" | "warning" | "danger";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "text-text-muted",
  success: "text-success",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
};

/** Una sola riga di stato sotto il nome della banca. Racconta cio' che conta
 * adesso (sincronizzazione, scadenza, errore, ultimo aggiornamento) e, quando
 * serve un'azione, diventa il pulsante per farla ("Rinnova", "Riprova"). Lo
 * stato non si affida al solo colore: ha sempre un'icona e un testo. */
export function ConnectionStatusLine({ connection, syncing, outcome, canSync, onRenew, onRetry }: Props) {
  const { t } = useTranslation("settings");
  const key = statusKeyOf(connection);
  const base = "items.bankConnections.page.connection";

  let tone: Tone = "neutral";
  let icon = <CircleCheck className="h-4 w-4 shrink-0" aria-hidden="true" />;
  let text: string;
  let action: { label: string; ariaLabel?: string; run: () => void } | null = null;

  if (syncing) {
    icon = <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />;
    text = t(`${base}.syncing`);
  } else if (key === "expired") {
    tone = "danger";
    icon = <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />;
    text = t(`${base}.statusLine.expired`);
    action = { label: t(`${base}.statusLine.renew`), ariaLabel: t(`${base}.renew`), run: onRenew };
  } else if (key === "expiring") {
    tone = "warning";
    icon = <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />;
    text = t(`${base}.statusLine.expiring`, { count: Math.max(connection.days_until_expiry ?? 0, 0) });
    action = { label: t(`${base}.statusLine.renew`), ariaLabel: t(`${base}.renew`), run: onRenew };
  } else if (key === "revoked" || key === "error") {
    tone = "danger";
    icon = <XCircle className="h-4 w-4 shrink-0" aria-hidden="true" />;
    text = t(`${base}.statusLine.${key}`);
  } else if (connection.last_error) {
    tone = "danger";
    icon = <XCircle className="h-4 w-4 shrink-0" aria-hidden="true" />;
    text =
      (t(`items.bankConnections.page.lastErrorsShort.${connection.last_error}`, { defaultValue: "" }) as string) ||
      t("items.bankConnections.page.lastErrorsShort.generic");
    if (canSync) {
      const retry = t(`${base}.statusLine.retry`);
      action = { label: retry, ariaLabel: `${text}. ${retry}`, run: onRetry };
    }
  } else if (outcome && !outcome.error) {
    tone = "success";
    text =
      outcome.imported > 0
        ? t(`${base}.syncDoneShort`, { count: outcome.imported })
        : t(`${base}.syncNoNewShort`);
  } else if (connection.last_sync_at) {
    tone = "success";
    text = t(`${base}.statusLine.upToDate`, { value: formatDateTime(connection.last_sync_at) });
  } else {
    icon = <CircleCheck className="h-4 w-4 shrink-0 opacity-50" aria-hidden="true" />;
    text = t(`${base}.statusLine.neverSynced`);
  }

  const boxed = tone === "warning" || tone === "danger";
  const content = (
    <>
      {icon}
      <span className="min-w-0 flex-1">{text}</span>
      {action && (
        <span className="inline-flex shrink-0 items-center gap-0.5 font-medium">
          {action.label}
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </span>
      )}
    </>
  );
  const classes = `flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-sm md:min-h-9 ${TONE_CLASSES[tone]} ${
    boxed ? "" : "px-0"
  }`;

  // aria-live: i cambi di stato (sync finita, errore) vengono annunciati senza spostare il focus.
  return (
    <div aria-live="polite">
      {action ? (
        <button type="button" onClick={action.run} aria-label={action.ariaLabel ?? action.label} className={classes}>
          {content}
        </button>
      ) : (
        <p className={classes}>{content}</p>
      )}
    </div>
  );
}
