import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { formatMoney } from "../../lib/format";
import { useChartTheme } from "./chartTheme";

export interface DonutSlice {
  label: string;
  value: number;
}

/** Donut spese/entrate per categoria o merchant (SPEC §45, SPEC_FE §16). */
export function DonutChart({ data, currency }: { data: DonutSlice[]; currency: string }) {
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
