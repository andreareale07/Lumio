import type { ComponentType } from "react";
import { ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ChartCard } from "../../components/charts/ChartCard";
import { EmptyState } from "../../components/ui/EmptyState";
import { clickableRowArrowClasses, clickableRowClasses } from "../../lib/clickableRow";
import { formatMoney } from "../../lib/format";
import type { MerchantBreakdownItem } from "../../types/api";

const MERCHANT_DISPLAY_LIMIT = 10;

/** Etichetta con cui `analytics.by_merchant` (backend) rietichetta le righe
 * con `merchant IS NULL`: il frontend la riconosce per usare `no_merchant`
 * invece di un match esatto sul testo. */
export const NO_MERCHANT_LABEL = "Senza merchant";

export interface SelectedMerchant {
  /** `null` = righe senza merchant. */
  merchant: string | null;
  label: string;
}

interface MerchantListProps {
  items: MerchantBreakdownItem[];
  currency: string;
  icon: ComponentType<{ className?: string }>;
  title: string;
  emptyDescription: string;
  onSelect: (selected: SelectedMerchant) => void;
}

/** Top merchant / Top sorgenti: stesso comportamento della gerarchia
 * categorie — ogni riga e' cliccabile e apre il drill-down (andamento +
 * transazioni) nel chiamante via `onSelect`. */
export function MerchantList({ items, currency, icon, title, emptyDescription, onSelect }: MerchantListProps) {
  const { t } = useTranslation(["analytics"]);

  const visible = items.slice(0, MERCHANT_DISPLAY_LIMIT);
  const others = items.slice(MERCHANT_DISPLAY_LIMIT);
  const othersTotal = others.reduce((sum, m) => sum + Number(m.total), 0);
  const maxTotal = Math.max(1, ...items.map((m) => Number(m.total)));
  const labelOf = (m: MerchantBreakdownItem) =>
    m.merchant === NO_MERCHANT_LABEL ? t("breakdown.merchants.noMerchant") : m.merchant;

  return (
    <ChartCard
      title={title}
      chartClassName="h-auto"
      empty={items.length === 0}
      emptyState={<EmptyState icon={icon} title={t("breakdown.merchants.emptyTitle")} description={emptyDescription} />}
      tableCaption={t("breakdown.merchants.tableCaption")}
      tableHeaders={t("breakdown.merchants.tableHeaders", { returnObjects: true }) as string[]}
      tableRows={items.map((m) => [
        labelOf(m),
        formatMoney(m.total, currency),
        `${Math.round(Number(m.share) * 100)}%`,
        m.transactions_count,
      ])}
    >
      <ul className="flex flex-col gap-3">
        {visible.map((m) => {
          const barPct = Math.round((Number(m.total) / maxTotal) * 100);
          return (
            <li key={m.merchant}>
              <button
                type="button"
                onClick={() =>
                  onSelect({ merchant: m.merchant === NO_MERCHANT_LABEL ? null : m.merchant, label: labelOf(m) })
                }
                className={`flex w-full flex-col gap-1 text-left ${clickableRowClasses}`}
              >
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate text-text">{labelOf(m)}</span>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-xs text-text-muted">{Math.round(Number(m.share) * 100)}%</span>
                    <span className="font-numeric text-text">{formatMoney(m.total, currency)}</span>
                    <ArrowUpRight className={clickableRowArrowClasses} aria-hidden="true" />
                  </div>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-hover">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${barPct}%` }} />
                </div>
              </button>
            </li>
          );
        })}
        {others.length > 0 && (
          <li className="flex items-center justify-between pt-1 text-sm text-text-muted">
            <span>{t("breakdown.merchants.othersRow", { count: others.length })}</span>
            <span className="font-numeric">{formatMoney(othersTotal, currency)}</span>
          </li>
        )}
      </ul>
    </ChartCard>
  );
}
