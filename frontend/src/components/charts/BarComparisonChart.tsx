import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatCompactMoney, formatMoney } from "../../lib/format";
import { useChartTheme } from "./chartTheme";

export interface CashFlowBarPoint {
  period: string;
  label: string;
  income: number;
  expenses: number;
}

/** Entrate vs uscite per periodo (SPEC §45, SPEC_FE §15). */
export function BarComparisonChart({ data, currency }: { data: CashFlowBarPoint[]; currency: string }) {
  const theme = useChartTheme();

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={theme.border} vertical={false} />
        <XAxis dataKey="label" stroke={theme.textMuted} tickLine={false} axisLine={false} fontSize={12} />
        <YAxis
          stroke={theme.textMuted}
          tickLine={false}
          axisLine={false}
          fontSize={12}
          width={64}
          tickFormatter={(value: number) => formatCompactMoney(value, currency)}
        />
        <Tooltip
          contentStyle={{
            background: theme.surface,
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            color: theme.text,
          }}
          labelStyle={{ color: theme.textMuted }}
          formatter={(value) => formatMoney(Number(value), currency)}
        />
        <Legend verticalAlign="top" align="left" height={24} wrapperStyle={{ fontSize: 12, color: theme.textMuted }} />
        <Bar dataKey="income" name="Entrate" fill={theme.success} radius={[4, 4, 0, 0]} />
        <Bar dataKey="expenses" name="Uscite" fill={theme.danger} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
