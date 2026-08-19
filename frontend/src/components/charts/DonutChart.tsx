import { useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { formatMoney } from "../../lib/format";
import { ChartLegend } from "./ChartLegend";
import { categoricalColor, useChartTheme } from "./chartTheme";

export interface DonutSlice {
  label: string;
  value: number;
  /** Chiave stabile per il drill-down (es. category_id) — non la stessa
   * `label` mostrata, che puo' ripetersi o cambiare senza cambiare
   * identita' (rework dashboard interattivo, click-to-drill-down). */
  key?: string;
  /** Quota 0..1 calcolata dal backend (serializzata come stringa, stessa
   * convenzione di `AllocationItem.share`) — se assente, la legenda la
   * calcola dal totale delle fette mostrate. */
  share?: string;
}

/** Donut spese/entrate per categoria o merchant (SPEC §45, SPEC_FE §16),
 * riusato anche per le distribuzioni del portfolio. `onSliceClick`
 * opzionale (rework dashboard interattivo, SPEC_FE §68): non ogni
 * chiamante ha un drill-down significativo per ogni fetta.
 *
 * `legend` e' opt-in (default `"none"` = comportamento identico a prima):
 * quando attivata, la legenda vive in DOM normale accanto/sotto il donut
 * (mai dentro l'SVG — vedi `ChartLegend` per il perche'), con lo stesso
 * colore delle fette (`categoricalColor`, unica fonte condivisa) e hover
 * sincronizzato in entrambe le direzioni. */
export function DonutChart({
  data,
  currency,
  onSliceClick,
  legend = "none",
  maxSlices,
}: {
  data: DonutSlice[];
  currency: string;
  onSliceClick?: (slice: DonutSlice) => void;
  legend?: "side" | "bottom" | "none";
  maxSlices?: number;
}) {
  const theme = useChartTheme();
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  // Oltre `maxSlices` fette, le eccedenti si aggregano in "Altri (N)" — mai
  // cliccabile (nessun drill-down significativo per piu' voci insieme).
  const aggregated = maxSlices !== undefined && data.length > maxSlices;
  const displayData: DonutSlice[] = aggregated
    ? [
        ...data.slice(0, maxSlices - 1),
        {
          label: `Altri (${data.length - (maxSlices - 1)})`,
          value: data.slice(maxSlices - 1).reduce((sum, slice) => sum + slice.value, 0),
        },
      ]
    : data;

  const hoverable = legend !== "none";

  const chart = (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie
          data={displayData}
          dataKey="value"
          nameKey="label"
          innerRadius="60%"
          outerRadius="90%"
          paddingAngle={2}
          stroke="none"
          onClick={onSliceClick ? (entry) => onSliceClick(entry as unknown as DonutSlice) : undefined}
          onMouseEnter={hoverable ? (_entry: unknown, index: number) => setActiveIndex(index) : undefined}
          onMouseLeave={hoverable ? () => setActiveIndex(null) : undefined}
          style={onSliceClick ? { cursor: "pointer" } : undefined}
        >
          {displayData.map((slice, i) => (
            <Cell
              key={slice.label}
              fill={categoricalColor(theme, i)}
              opacity={activeIndex !== null && activeIndex !== i ? 0.35 : 1}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: theme.surface,
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            color: theme.text,
          }}
          formatter={(value, name) => [formatMoney(Number(value), currency), String(name)] as [string, string]}
        />
      </PieChart>
    </ResponsiveContainer>
  );

  if (legend === "none") {
    return chart;
  }

  const legendItems = displayData.map((slice) => ({
    key: slice.key,
    label: slice.label,
    value: slice.value,
    share: slice.share !== undefined ? Number(slice.share) : undefined,
  }));

  return (
    <div className={legend === "side" ? "flex h-full flex-col gap-3 sm:flex-row sm:items-stretch" : "flex h-full flex-col gap-3"}>
      <div className={legend === "side" ? "h-40 w-full shrink-0 sm:h-auto sm:w-1/2 lg:w-3/5" : "h-40 w-full shrink-0"}>
        {chart}
      </div>
      <ChartLegend
        items={legendItems}
        theme={theme}
        currency={currency}
        activeIndex={activeIndex}
        onHoverIndex={setActiveIndex}
        onItemClick={
          onSliceClick
            ? (_item, index) => {
                // La fetta "Altri" aggregata non ha un drill-down significativo.
                if (aggregated && index === displayData.length - 1) return;
                onSliceClick(displayData[index]);
              }
            : undefined
        }
      />
    </div>
  );
}
