import { useTranslation } from "react-i18next";

import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { ActivityRow } from "./ActivityRow";
import { useActivity } from "./api";

/** Cruscotto "Attività": elenco unico di tutte le elaborazioni del
 * workspace — import in corso (+ la loro classificazione AI), l'ultima
 * riclassificazione, e l'ultima esecuzione dei job schedulati (refresh
 * prezzi, snapshot, export Google Sheets) — con dettaglio narrativo live
 * per i job che lo emettono (vedi activity_service.py). Richiesta
 * dall'utente per rispondere a "cosa sta facendo il sistema ora?" senza
 * dover andare a cercare in pagine diverse. */
export function ActivityPage() {
  const { t } = useTranslation("activity");
  const { data: items, isLoading, isError, refetch } = useActivity();

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-text">{t("page.title")}</h1>
        <p className="text-sm text-text-muted">{t("page.description")}</p>
      </div>

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState message={t("page.loadError")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && items && items.length === 0 && (
        <p className="text-sm text-text-muted">{t("page.empty")}</p>
      )}

      {!isLoading && !isError && items && items.length > 0 && (
        <div className="flex flex-col gap-2">
          {items.map((item) => (
            <ActivityRow key={`${item.kind}-${item.events_url ?? item.started_at ?? item.label}`} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
