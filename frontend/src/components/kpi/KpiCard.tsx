import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { Card } from "../ui/Card";
import { formatMoney, formatPercent, formatSignedMoney } from "../../lib/format";
import { Sparkline } from "../charts/Sparkline";

interface KpiCardProps {
  title: string;
  value: string;
  currency: string;
  previousValue?: string;
  comparisonLabel?: string;
  /** Un aumento e' un buon segnale (Entrate, Cash Flow) o un cattivo segnale
   * (Spese)? Determina il colore della variazione, non la sua direzione. */
  positiveIsGood?: boolean;
  /** Serie storica per il mini-trend (SPEC_FE §13) — opzionale: non ogni
   * KPI ha oggi un endpoint che ne calcoli lo storico (es. Investimenti,
   * Debiti), meglio ometterlo che inventare un trend con un solo punto. */
  sparklineValues?: number[];
  /** Mostra il segno esplicito (+/-) sul valore principale, mai affidato
   * solo al colore (SPEC_FE §66) — per KPI che sono gia' una differenza
   * (Rendimento, Utile realizzato), non un totale assoluto. Default
   * `false`, comportamento invariato per ogni chiamante esistente. */
  signed?: boolean;
  onClick?: () => void;
}

/** KPI card con variazione vs periodo precedente (SPEC_FE §13). */
export function KpiCard({
  title,
  value,
  currency,
  previousValue,
  comparisonLabel,
  positiveIsGood = true,
  sparklineValues,
  signed = false,
  onClick,
}: KpiCardProps) {
  const current = Number(value);
  const previous = previousValue !== undefined ? Number(previousValue) : undefined;
  const change = previous !== undefined && previous !== 0 ? (current - previous) / Math.abs(previous) : undefined;
  const trend: "up" | "down" | "flat" = !change ? "flat" : change > 0 ? "up" : "down";
  const isGood = trend === "flat" ? null : positiveIsGood ? trend === "up" : trend === "down";
  const sparklineTone = trend === "flat" ? "primary" : isGood ? "success" : "danger";

  const content = (
    <Card className={`flex flex-col gap-1 ${onClick ? "cursor-pointer hover:bg-surface-hover" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm text-text-muted">{title}</span>
        {sparklineValues && <Sparkline values={sparklineValues} tone={sparklineTone} />}
      </div>
      <span className="font-numeric text-2xl font-semibold text-text">
        {signed ? formatSignedMoney(current, currency) : formatMoney(current, currency)}
      </span>
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

  if (!onClick) return content;
  return (
    <button type="button" onClick={onClick} className="text-left">
      {content}
    </button>
  );
}
