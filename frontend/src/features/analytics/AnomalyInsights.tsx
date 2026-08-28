import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatDate, formatMoney, formatPercent } from "../../lib/format";
import type { AnalyticsDirection, Anomaly } from "../../types/api";
import { useAnomalies, useDismissDetection, useUndoDetectionOverride } from "./api";

interface AnomalyInsightsProps {
  direction: AnalyticsDirection;
  dateFrom?: string;
  dateTo?: string;
}

/** Card "Anomalie" (piano `synchronous-chasing-pike.md`, FETTA 2 §1.2(d) di
 * FETTA 1). A differenza di `RecurringInsights`, segue il periodo corrente
 * della pagina (`dateFrom`/`dateTo`) — la baseline statistica resta sempre
 * a 12 mesi lato backend (`anomalies.data.baseline`), qui si mostrano solo
 * le anomalie DENTRO il periodo richiesto. Componente pronto da importare,
 * NON montato qui dentro `BreakdownPage.tsx`. */
export function AnomalyInsights({ direction, dateFrom, dateTo }: AnomalyInsightsProps) {
  const { t } = useTranslation(["analytics", "enums"]);
  const anomalies = useAnomalies({ direction, date_from: dateFrom, date_to: dateTo });
  const dismiss = useDismissDetection();
  const undo = useUndoDetectionOverride();

  if (anomalies.isLoading) {
    return (
      <Card className="flex flex-col gap-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </Card>
    );
  }

  if (anomalies.isError) {
    return <ErrorState message={t("breakdown.errorMessage")} onRetry={() => void anomalies.refetch()} />;
  }

  if (!anomalies.data) return null;

  const currency = anomalies.data.currency;
  const items = anomalies.data.items;

  return (
    <Card className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-text">{t("anomalies.title")}</h3>
        <div className="text-sm text-text-muted">{t("anomalies.subtitle")}</div>
      </div>

      {anomalies.data.insufficient_data ? (
        <p className="text-sm text-text-muted">{t("anomalies.insufficientData")}</p>
      ) : items.length === 0 ? (
        <EmptyState title={t("anomalies.emptyTitle")} description={t("anomalies.emptyDescription")} />
      ) : (
        <>
          <p className="text-xs text-text-muted">{t("anomalies.baselineNote")}</p>
          <ul className="flex flex-col gap-1">
            {items.map((item) => (
              <AnomalyRow
                key={item.transaction_id}
                item={item}
                currency={currency}
                onDismiss={() => dismiss.mutate({ override_type: "anomaly", transaction_id: item.transaction_id })}
                isDismissing={dismiss.isPending}
              />
            ))}
          </ul>
        </>
      )}

      {dismiss.isSuccess && (
        <button
          type="button"
          className="self-start text-xs text-primary hover:underline"
          onClick={() => {
            const id = dismiss.data?.id;
            if (id) undo.mutate(id);
          }}
        >
          {t("recurring.undo")}
        </button>
      )}
    </Card>
  );
}

function AnomalyRow({
  item,
  currency,
  onDismiss,
  isDismissing,
}: {
  item: Anomaly;
  currency: string;
  onDismiss: () => void;
  isDismissing: boolean;
}) {
  const { t } = useTranslation(["analytics", "enums"]);
  const vsKey = item.anomaly_type === "category_outlier" ? "anomalies.vsCategory" : "anomalies.vsSeries";

  return (
    <li className="group flex items-center justify-between gap-3 rounded-lg px-3 py-2 hover:bg-surface-hover">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm text-text">{item.label}</span>
          <Badge tone="warning">{t(`enums:anomalyType.${item.anomaly_type}`)}</Badge>
        </div>
        <div className="text-xs text-text-muted">
          {formatDate(item.transaction_date)}
          {item.deviation_pct !== null && (
            <> · {t(vsKey, { value: formatPercent(item.deviation_pct, { signed: true }) })}</>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="font-numeric text-sm text-text">{formatMoney(item.amount, currency)}</span>
        <button
          type="button"
          disabled={isDismissing}
          onClick={onDismiss}
          className="text-xs text-text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100 disabled:opacity-50"
        >
          {t("anomalies.ignore")}
        </button>
      </div>
    </li>
  );
}
