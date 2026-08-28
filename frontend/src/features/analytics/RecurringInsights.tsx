import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatDate, formatMoney } from "../../lib/format";
import type { AnalyticsDirection, RecurringSeries } from "../../types/api";
import { useDismissDetection, useRecurringSeries, useUndoDetectionOverride } from "./api";

interface RecurringInsightsProps {
  direction: AnalyticsDirection;
}

/** Card "Ricorrenze" (piano `synchronous-chasing-pike.md`, FETTA 2 §1.2(d)
 * di FETTA 1 — montata da `BreakdownPage.tsx` fra la gerarchia categorie e i
 * top merchant). Nessun filtro periodo: l'endpoint copre sempre 25 mesi
 * indietro da oggi, la ricorrenza non ha senso su un solo mese (vedi
 * `useRecurringSeries`). */
export function RecurringInsights({ direction }: RecurringInsightsProps) {
  const { t } = useTranslation(["analytics", "enums"]);
  const series = useRecurringSeries({ direction });
  const dismiss = useDismissDetection();
  const undo = useUndoDetectionOverride();

  if (series.isLoading) {
    return (
      <Card className="flex flex-col gap-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </Card>
    );
  }

  if (series.isError) {
    return <ErrorState message={t("breakdown.errorMessage")} onRetry={() => void series.refetch()} />;
  }

  if (!series.data) return null;

  const currency = series.data.currency;
  const items = series.data.items;

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-text">{t("recurring.title")}</h3>
          <div className="text-sm text-text-muted">{t("recurring.subtitle")}</div>
        </div>
        {items.some((i) => i.status === "active") && (
          <span className="font-numeric text-sm font-medium text-text">
            {t("recurring.monthlyTotal", { value: formatMoney(series.data.monthly_total, currency) })}
          </span>
        )}
      </div>

      {series.data.insufficient_data ? (
        <p className="text-sm text-text-muted">{t("recurring.insufficientData")}</p>
      ) : items.length === 0 ? (
        <EmptyState title={t("recurring.emptyTitle")} description={t("recurring.emptyDescription")} />
      ) : (
        <ul className="flex flex-col gap-1">
          {items.map((item) => (
            <RecurringRow
              key={item.series_key}
              item={item}
              currency={currency}
              onDismiss={() =>
                dismiss.mutate({ override_type: "recurring_series", series_key: item.series_key })
              }
              isDismissing={dismiss.isPending}
            />
          ))}
        </ul>
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

function RecurringRow({
  item,
  currency,
  onDismiss,
  isDismissing,
}: {
  item: RecurringSeries;
  currency: string;
  onDismiss: () => void;
  isDismissing: boolean;
}) {
  const { t } = useTranslation(["analytics", "enums"]);
  const amountLabel =
    item.expected_next_amount !== null ? formatMoney(item.expected_next_amount, currency) : t("recurring.variableAmount");

  return (
    <li className="group flex items-center justify-between gap-3 rounded-lg px-3 py-2 hover:bg-surface-hover">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm text-text">{item.label}</span>
          <Badge tone="neutral">{t(`enums:cadence.${item.cadence}`)}</Badge>
          {item.status === "ended" && <Badge tone="neutral">{t("recurring.ended")}</Badge>}
          {item.amount_is_variable && !item.price_change && (
            <span className="text-xs text-text-muted">{t("recurring.variableAmount")}</span>
          )}
          {item.price_change && (
            <Badge tone="warning">
              {t("recurring.priceChange", {
                old: formatMoney(item.price_change.old_amount, currency),
                new: formatMoney(item.price_change.new_amount, currency),
                date: formatDate(item.price_change.changed_at),
              })}
            </Badge>
          )}
        </div>
        {item.status === "active" && (
          <div className="text-xs text-text-muted">
            {t("recurring.nextExpected", { date: formatDate(item.expected_next_date) })}
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className="font-numeric text-sm text-text">{amountLabel}</span>
        <button
          type="button"
          disabled={isDismissing}
          onClick={onDismiss}
          className="text-xs text-text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100 disabled:opacity-50"
        >
          {t("recurring.dismiss")}
        </button>
      </div>
    </li>
  );
}
