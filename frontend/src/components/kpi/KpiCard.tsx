import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { Card } from "../ui/Card";
import { formatMoney, formatPercent } from "../../lib/format";

interface KpiCardProps {
  title: string;
  value: string;
  currency: string;
  previousValue?: string;
  comparisonLabel?: string;
  /** Un aumento e' un buon segnale (Entrate, Cash Flow) o un cattivo segnale
   * (Spese)? Determina il colore della variazione, non la sua direzione. */
  positiveIsGood?: boolean;
}

/** KPI card con variazione vs periodo precedente (SPEC_FE §13). */
export function KpiCard({
  title,
  value,
  currency,
  previousValue,
  comparisonLabel,
  positiveIsGood = true,
}: KpiCardProps) {
  const current = Number(value);
  const previous = previousValue !== undefined ? Number(previousValue) : undefined;
  const change = previous !== undefined && previous !== 0 ? (current - previous) / Math.abs(previous) : undefined;
  const trend: "up" | "down" | "flat" = !change ? "flat" : change > 0 ? "up" : "down";
  const isGood = trend === "flat" ? null : positiveIsGood ? trend === "up" : trend === "down";

  return (
    <Card className="flex flex-col gap-1">
      <span className="text-sm text-text-muted">{title}</span>
      <span className="font-numeric text-2xl font-semibold text-text">{formatMoney(current, currency)}</span>
      {trend !== "flat" && change !== undefined && (
        <div className="flex flex-wrap items-center gap-1 text-sm">
          <span className={`flex items-center gap-0.5 ${isGood ? "text-success" : "text-danger"}`}>
            {trend === "up" ? (
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ArrowDownRight className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {formatPercent(change)}
          </span>
          {comparisonLabel && <span className="text-text-muted">{comparisonLabel}</span>}
        </div>
      )}
    </Card>
  );
}
