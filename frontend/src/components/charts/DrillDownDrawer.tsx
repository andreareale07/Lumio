import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import { Drawer } from "../ui/Drawer";
import { Skeleton } from "../ui/Skeleton";
import { formatDate, formatMoney, formatPercent, formatSignedMoney } from "../../lib/format";
import { AreaTrendChart, type TrendPoint } from "./AreaTrendChart";

export interface DrillDownBreakdownItem {
  key: string;
  label: string;
  value: number;
}

export interface DrillDownTransaction {
  id: string;
  label: string;
  date: string;
  amount: string;
  currency: string;
}

export interface DrillDownComparison {
  current: number;
  previous: number;
  /** `false` per una spesa (un aumento e' una cattiva notizia, colorato di
   * rosso) — coerente con `isGoodChange` gia' calcolato oggi in
   * `BreakdownPage.tsx` per l'header della pagina, qui riapplicato alla
   * singola voce del drill-down invece che al totale. */
  higherIsGood: boolean;
}

interface DrillDownDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  currency: string;
  isLoading?: boolean;
  comparison?: DrillDownComparison;
  trend?: TrendPoint[];
  breakdownTitle?: string;
  breakdown?: DrillDownBreakdownItem[];
  transactions?: DrillDownTransaction[];
  viewAllHref?: string;
  viewAllLabel?: string;
}

/**
 * Pannello di drill-down generico (rework dashboard interattivo): stesse 4
 * sezioni opzionali riusate da Dashboard/Spese/Entrate/Investimenti/
 * Patrimonio con dati diversi — chi lo apre decide COSA passare, questo
 * componente non sa nulla di categorie/merchant/asset. Costruito sopra
 * `Drawer.tsx` esistente (stesso pattern di `TransactionDetailDrawer.tsx`),
 * non un nuovo sistema di pannelli.
 *
 * Sintesi di SPEC_FE §30 (dettaglio ricco: trend + breakdown + transazioni +
 * confronto) e §68 (click-to-filter): `viewAllHref` porta alla lista
 * Movimenti gia' filtrata per chi vuole scendere oltre il riepilogo qui
 * dentro, senza che aprire il drawer faccia mai perdere il contesto della
 * pagina di partenza.
 */
export function DrillDownDrawer({
  open,
  onClose,
  title,
  currency,
  isLoading,
  comparison,
  trend,
  breakdownTitle,
  breakdown,
  transactions,
  viewAllHref,
  viewAllLabel = "Vedi tutte le transazioni",
}: DrillDownDrawerProps) {
  const change =
    comparison && comparison.previous !== 0 ? (comparison.current - comparison.previous) / Math.abs(comparison.previous) : undefined;
  const isIncrease = change !== undefined && change > 0;
  const isGoodChange = comparison && change !== undefined && change !== 0 ? (comparison.higherIsGood ? isIncrease : !isIncrease) : null;

  const maxBreakdownValue = breakdown?.reduce((max, item) => Math.max(max, item.value), 0) ?? 0;

  return (
    <Drawer open={open} onClose={onClose} title={title}>
      <div className="flex flex-col gap-5">
        {isLoading && (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-8 w-32" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}

        {!isLoading && comparison && (
          <div className="flex items-baseline gap-2">
            <span className="font-numeric text-2xl font-semibold text-text">
              {formatMoney(comparison.current, currency)}
            </span>
            {change !== undefined && change !== 0 && (
              <span className={`text-sm ${isGoodChange ? "text-success" : "text-danger"}`}>
                {formatPercent(change, { signed: true })} vs periodo precedente
              </span>
            )}
          </div>
        )}

        {!isLoading && trend && trend.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text">Andamento</h3>
            <div className="h-32">
              <AreaTrendChart data={trend} currency={currency} />
            </div>
          </div>
        )}

        {!isLoading && breakdown && breakdown.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text">{breakdownTitle ?? "Dettaglio"}</h3>
            <ul className="flex flex-col gap-2">
              {breakdown.map((item) => (
                <li key={item.key} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-text">{item.label}</span>
                    <span className="font-numeric text-text-muted">{formatMoney(item.value, currency)}</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-hover">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: maxBreakdownValue > 0 ? `${(item.value / maxBreakdownValue) * 100}%` : "0%" }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {!isLoading && transactions && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text">Transazioni recenti</h3>
            {transactions.length === 0 && <p className="text-sm text-text-muted">Nessuna transazione.</p>}
            {transactions.length > 0 && (
              <ul className="flex flex-col gap-2">
                {transactions.map((t) => (
                  <li key={t.id} className="flex items-center justify-between rounded-lg border border-border p-2.5 text-sm">
                    <div className="flex flex-col">
                      <span className="text-text">{t.label}</span>
                      <span className="text-text-muted">{formatDate(t.date)}</span>
                    </div>
                    <span className="font-numeric text-text">{formatSignedMoney(t.amount, t.currency)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {!isLoading && viewAllHref && (
          <Link
            to={viewAllHref}
            onClick={onClose}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border p-2.5 text-sm font-medium text-primary hover:bg-surface-hover"
          >
            {viewAllLabel}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        )}
      </div>
    </Drawer>
  );
}
