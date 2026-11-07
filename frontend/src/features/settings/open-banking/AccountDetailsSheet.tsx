import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, History } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { BottomSheet } from "../../../components/ui/BottomSheet";
import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { formatDate, formatDateTime } from "../../../lib/format";
import { useIsDesktop } from "../../../lib/useIsDesktop";
import type { BankConnectionAccount } from "../../../types/api";

interface Props {
  account: BankConnectionAccount | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onResync: () => void;
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <li className="flex min-h-9 items-baseline justify-between gap-4 py-1.5 text-sm">
      <span className="text-text-muted">{label}</span>
      <span className="font-medium text-text">{value}</span>
    </li>
  );
}

const sum = (values: (number | undefined)[]) => values.reduce<number>((total, value) => total + (value ?? 0), 0);

/** "Dettagli sync" di un conto: statistiche dell'ultima lettura (solo conteggi, mai
 * valori) e "Rileggi storico", la via di recupero esplicita dopo qualunque errore. */
export function AccountDetailsSheet({ account, loading, error, onClose, onResync }: Props) {
  const { t } = useTranslation(["settings", "common"]);
  const isDesktop = useIsDesktop();
  const [confirming, setConfirming] = useState(false);
  const open = account !== null;

  useEffect(() => {
    if (open) setConfirming(false);
  }, [open]);

  const close = useCallback(() => onClose(), [onClose]);
  if (!account) return null;

  const base = "settings:items.bankConnections.page.diagnostics";
  const stats = account.last_sync_stats ?? null;
  const fetch = stats?.fetch;
  const persist = stats?.persist ?? {};
  const gaps = account.balance_snapshot?.continuity_gaps ?? 0;
  const title = account.name ?? account.product ?? t(`${base}.untitled`);
  const alreadyKnown = sum([persist.known_duplicate, persist.repeated_in_batch, persist.duplicate_by_fingerprint]);
  const discarded = Object.entries(fetch?.discarded ?? {});
  const flags = Object.entries(fetch?.flags ?? {}).filter(([key]) => !key.startsWith("has_"));
  const subCodes = Object.entries(fetch?.sub_codes ?? {});

  const content = (
    <div className="flex flex-col gap-4">
      {gaps > 0 && (
        <p role="alert" className="flex items-start gap-2 rounded-lg border border-border p-3 text-sm text-danger">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t(`${base}.balanceGap`, { count: gaps })}</span>
        </p>
      )}

      {stats?.error && (
        <p role="alert" className="text-sm text-danger">
          {t(`settings:items.bankConnections.page.lastErrors.${stats.error}`, {
            defaultValue: t("settings:items.bankConnections.page.lastErrors.generic"),
          })}
        </p>
      )}

      {!stats || (!fetch && !stats.error) ? (
        <p className="text-sm text-text-muted">{t(`${base}.noData`)}</p>
      ) : (
        fetch && (
          <>
            <p className="text-sm text-text-muted">
              {stats.at ? t(`${base}.lastRead`, { value: formatDateTime(stats.at) }) : null}{" "}
              {fetch.strategy === "longest"
                ? t(`${base}.windowLongest`)
                : t(`${base}.windowFrom`, { date: fetch.date_from ? formatDate(fetch.date_from) : "—" })}
            </p>
            <ul className="divide-y divide-border">
              <Row label={t(`${base}.read`)} value={fetch.raw_count} />
              <Row label={t(`${base}.imported`)} value={persist.imported ?? 0} />
              <Row label={t(`${base}.alreadyKnown`)} value={alreadyKnown} />
              <Row label={t(`${base}.inReview`)} value={(persist.in_review ?? 0) + (persist.review_known ?? 0)} />
              {(persist.tombstoned ?? 0) > 0 && <Row label={t(`${base}.tombstoned`)} value={persist.tombstoned} />}
              {(persist.foreign_currency ?? 0) > 0 && (
                <Row label={t(`${base}.foreignCurrency`)} value={persist.foreign_currency} />
              )}
              {(persist.id_reused_distinct ?? 0) > 0 && (
                <Row label={t(`${base}.idReused`)} value={persist.id_reused_distinct} />
              )}
              {discarded.map(([reason, count]) => (
                <Row
                  key={reason}
                  label={t(`${base}.discarded.${reason}`, { defaultValue: reason })}
                  value={count}
                />
              ))}
            </ul>
            {(flags.length > 0 || subCodes.length > 0) && (
              <div className="text-sm text-text-muted">
                <p className="font-medium text-text">{t(`${base}.technical`)}</p>
                <ul className="mt-1 flex flex-col gap-0.5">
                  {flags.map(([flag, count]) => (
                    <li key={flag}>{t(`${base}.flags.${flag}`, { defaultValue: flag })}: {count}</li>
                  ))}
                  {subCodes.length > 0 && (
                    <li>{t(`${base}.subCodes`)}: {subCodes.map(([code, count]) => `${code} ×${count}`).join(", ")}</li>
                  )}
                  <li>{t(`${base}.pages`, { count: fetch.pages })}</li>
                </ul>
              </div>
            )}
          </>
        )
      )}

      <div className="rounded-lg border border-border p-3">
        <p className="flex items-center gap-2 text-sm font-medium text-text">
          <History className="h-4 w-4" aria-hidden="true" />
          {t(`${base}.resync.title`)}
        </p>
        <p className="mt-1 text-sm text-text-muted">{t(`${base}.resync.body`)}</p>
        {confirming ? (
          <>
            <p role="note" className="mt-2 text-sm text-text-muted">
              {t(`${base}.resync.limits`)}
            </p>
            <div className="mt-3 flex gap-2">
              <Button variant="secondary" onClick={() => setConfirming(false)} className="flex-1 sm:flex-none">
                {t("common:actions.cancel")}
              </Button>
              <Button loading={loading} onClick={onResync} className="flex-1 sm:flex-none">
                {t(`${base}.resync.confirm`)}
              </Button>
            </div>
          </>
        ) : (
          <Button variant="secondary" onClick={() => setConfirming(true)} className="mt-3 w-full sm:w-auto">
            {t(`${base}.resync.action`)}
          </Button>
        )}
        {error && (
          <p role="alert" className="mt-2 text-sm text-danger">
            {error}
          </p>
        )}
      </div>
    </div>
  );

  if (!isDesktop) {
    return (
      <BottomSheet open onClose={close} title={t(`${base}.title`, { account: title })}>
        <div className="pb-4 pt-3">{content}</div>
      </BottomSheet>
    );
  }
  return (
    <Dialog open onClose={close} title={t(`${base}.title`, { account: title })}>
      {content}
    </Dialog>
  );
}
