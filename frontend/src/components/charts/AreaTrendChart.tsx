import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatCompactMoney, formatMoney } from "../../lib/format";
import { useChartTheme } from "./chartTheme";

export interface TrendPoint {
  period: string;
  label: string;
  value: number;
}

/** Grafico area/line del patrimonio nel tempo (SPEC §45, SPEC_FE §14). */
export function AreaTrendChart({ data, currency }: { data: TrendPoint[]; currency: string }) {
  const theme = useChartTheme();

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="lumio-area-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={theme.primary} stopOpacity={0.35} />
            <stop offset="95%" stopColor={theme.primary} stopOpacity={0} />
          </linearGradient>
        </defs>
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
          formatter={(value) => [formatMoney(Number(value), currency), "Saldo"] as [string, string]}
        />
        <Area type="monotone" dataKey="value" stroke={theme.primary} strokeWidth={2} fill="url(#lumio-area-fill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
