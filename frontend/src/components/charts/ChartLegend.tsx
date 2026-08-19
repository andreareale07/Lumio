import { formatMoney, formatPercent } from "../../lib/format";
import { categoricalColor, type ChartTheme } from "./chartTheme";

export interface ChartLegendItem {
  key?: string;
  label: string;
  value: number;
  /** Quota 0..1 calcolata dal backend, quando disponibile — mai
   * ricalcolata qui: un valore fornito dal server non puo' mai divergere
   * da quello mostrato altrove nella stessa pagina. Se assente, si calcola
   * dal totale degli `items` passati (va bene per un donut isolato, dove
   * il totale coincide). */
  share?: number;
}

/** Legenda in DOM normale (mai dentro l'SVG del donut): swatch colorato +
 * etichetta + valore + quota, nello stesso ordine e con lo stesso colore
 * delle fette (`categoricalColor`, unica fonte condivisa — non puo' mai
 * disallinearsi). Righe interattive (focusabili da tastiera) solo se
 * `onItemClick` e' passato, altrimenti sola lettura. */
export function ChartLegend({
  items,
  theme,
  currency,
  activeIndex = null,
  onHoverIndex,
  onItemClick,
}: {
  items: ChartLegendItem[];
  theme: ChartTheme;
  currency: string;
  activeIndex?: number | null;
  onHoverIndex?: (index: number | null) => void;
  onItemClick?: (item: ChartLegendItem, index: number) => void;
}) {
  const total = items.reduce((sum, item) => sum + item.value, 0);

  return (
    <ul className="flex min-w-0 flex-1 flex-col gap-0.5 overflow-y-auto">
      {items.map((item, index) => {
        const share = item.share ?? (total !== 0 ? item.value / total : 0);
        const color = categoricalColor(theme, index);
        const dimmed = activeIndex !== null && activeIndex !== index;
        const rowClassName = `flex items-center gap-2 rounded-md px-1.5 py-1 text-sm transition-opacity ${
          dimmed ? "opacity-40" : ""
        }`;
        const row = (
          <>
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ backgroundColor: color }}
              aria-hidden="true"
            />
            <span className="min-w-0 flex-1 truncate text-text" title={item.label}>
              {item.label}
            </span>
            <span className="font-numeric shrink-0 text-text">{formatMoney(item.value, currency)}</span>
            <span className="font-numeric w-12 shrink-0 text-right text-text-muted">{formatPercent(share)}</span>
          </>
        );
        const hoverHandlers = onHoverIndex
          ? { onMouseEnter: () => onHoverIndex(index), onMouseLeave: () => onHoverIndex(null) }
          : undefined;

        if (onItemClick) {
          return (
            <li key={item.key ?? item.label}>
              <button
                type="button"
                className={`${rowClassName} w-full text-left hover:bg-surface-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary`}
                onClick={() => onItemClick(item, index)}
                aria-label={`${item.label}: ${formatMoney(item.value, currency)}, ${formatPercent(share)}`}
                {...hoverHandlers}
              >
                {row}
              </button>
            </li>
          );
        }
        return (
          <li key={item.key ?? item.label} className={rowClassName} {...hoverHandlers}>
            {row}
          </li>
        );
      })}
    </ul>
  );
}
