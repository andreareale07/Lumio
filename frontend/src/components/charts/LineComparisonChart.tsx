import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatCompactMoney, formatMoney } from "../../lib/format";
import { useChartTheme } from "./chartTheme";

export interface LineComparisonPoint {
  period: string;
  label: string;
  [key: string]: number | string;
}

export interface LineSeriesDef {
  key: string;
  label: string;
  tone: "success" | "danger" | "primary" | "muted";
  /** Linea tratteggiata (es. la mediana mobile "tipico") invece che piena. */
  dashed?: boolean;
}

/** Confronto multi-serie nel tempo a linee (redesign Dashboard/Spese/Entrate,
 * FETTA 1) — sostituisce il grafico a barre entrate/uscite della Dashboard
 * (`BarComparisonChart`, lasciato INTATTO: ha un secondo call site in
 * `AccountDetailPage.tsx` che non deve regredire) e alimenta anche il
 * grafico Andamento di Spese/Entrate (valore + mediana mobile tratteggiata).
 *
 * `label` per serie e' OBBLIGATORIA (non un default in italiano): il default
 * italiano hardcoded di `BarComparisonChart` era esattamente il bug i18n gia'
 * corretto una volta (la legenda di Recharts bypassa `t()`, va sempre
 * passata dal chiamante) — qui non si replica lo stesso errore. */
export function LineComparisonChart({
  data,
  series,
  currency,
  onPointClick,
}: {
  data: LineComparisonPoint[];
  series: LineSeriesDef[];
  currency: string;
  onPointClick?: (point: LineComparisonPoint) => void;
}) {
  const theme = useChartTheme();
  const toneColor: Record<LineSeriesDef["tone"], string> = {
    success: theme.success,
    danger: theme.danger,
    primary: theme.primary,
    muted: theme.textMuted,
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart
        data={data}
        margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
        onClick={(state) => {
          // Recharts v3: l'evento click del chart non porta piu' `activePayload`
          // (rimosso rispetto a v2) — l'indice nel `data` passato come prop e'
          // l'unico riferimento affidabile all'entrata attiva.
          const rawIndex = state?.activeIndex;
          const index = typeof rawIndex === "number" ? rawIndex : Number(rawIndex);
          const point = Number.isFinite(index) ? data[index] : undefined;
          if (point && onPointClick) onPointClick(point);
        }}
        style={onPointClick ? { cursor: "pointer" } : undefined}
      >
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
          formatter={(value, name) => [formatMoney(Number(value), currency), name] as [string, string]}
        />
        <Legend verticalAlign="top" align="left" height={24} wrapperStyle={{ fontSize: 12, color: theme.textMuted }} />
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={toneColor[s.tone]}
            strokeWidth={2}
            strokeDasharray={s.dashed ? "4 4" : undefined}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
