import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { formatMoney } from "../../lib/format";
import { useChartTheme } from "./chartTheme";

export interface DonutSlice {
  label: string;
  value: number;
  /** Chiave stabile per il drill-down (es. category_id) — non la stessa
   * `label` mostrata, che puo' ripetersi o cambiare senza cambiare
   * identita' (rework dashboard interattivo, click-to-drill-down). */
  key?: string;
}

/** Donut spese/entrate per categoria o merchant (SPEC §45, SPEC_FE §16).
 * `onSliceClick` opzionale (rework dashboard interattivo, SPEC_FE §68): non
 * ogni chiamante ha un drill-down significativo per ogni fetta (es. "Senza
 * categoria" non porta da nessuna parte). */
export function DonutChart({
  data,
  currency,
  onSliceClick,
}: {
  data: DonutSlice[];
  currency: string;
  onSliceClick?: (slice: DonutSlice) => void;
}) {
  const theme = useChartTheme();

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="label"
          innerRadius="60%"
          outerRadius="90%"
          paddingAngle={2}
          stroke="none"
          onClick={onSliceClick ? (entry) => onSliceClick(entry as unknown as DonutSlice) : undefined}
          style={onSliceClick ? { cursor: "pointer" } : undefined}
        >
          {data.map((slice, i) => (
            <Cell key={slice.label} fill={theme.categorical[i % theme.categorical.length]} />
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
}
