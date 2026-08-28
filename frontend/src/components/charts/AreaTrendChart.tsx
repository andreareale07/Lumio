import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatCompactMoney, formatMoney, formatPercent } from "../../lib/format";
import { useChartTheme } from "./chartTheme";

export interface TrendPoint {
  period: string;
  label: string;
  value: number;
}

/** Grafico area/line generico per un trend nel tempo (SPEC §45, SPEC_FE
 * §14) — riusato per contesti molto diversi (patrimonio, spese/entrate per
 * categoria, valore portfolio, trend nel drawer di drill-down): "Saldo" era
 * sbagliato ovunque tranne per un vero saldo conto (unico caso che lo passa
 * esplicitamente, vedi AccountDetailPage.tsx), quindi il default e'
 * generico. `format="percent"` (usato dal grafico di rendimento portfolio,
 * dove `value` e' una frazione tipo 0.10 non un importo) e' additivo: ogni
 * chiamante esistente non lo passa e resta sul default `"currency"`, zero
 * regressioni. In modalita' percentuale `currency` non serve (puo' restare
 * assente) e compare una linea di riferimento a 0% — senza, un rendimento
 * che oscilla vicino allo zero sarebbe illeggibile (sopra o sotto la
 * baseline?). */
// "tight" (stile Trade Republic, usato dal grafico prezzo titolo in
// AssetDetailPage): l'asse Y parte dal range EFFETTIVO dei dati (con un
// margine del 10%) invece che da zero — un titolo che oscilla tra 250 e
// 360 mostra davvero il movimento, invece di schiacciarlo in una fascia
// stretta in alto su una scala 0-360. Resta "zero" per default ovunque
// altrove (patrimonio, spese/entrate): li' la scala assoluta conta quanto
// l'andamento, un default diverso qui romperebbe quella lettura senza che
// nessuno l'abbia chiesto.
//
// Calcolato direttamente dai dati (non tramite le funzioni di dominio di
// Recharts, che ricevono un solo estremo alla volta — non abbastanza per
// un margine proporzionale al range che serve ENTRAMBI gli estremi
// insieme).
function tightDomain(data: TrendPoint[]): [number, number] | undefined {
  if (data.length === 0) return undefined;
  const values = data.map((d) => d.value);
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const range = dataMax - dataMin;
  const padding = range > 0 ? range * 0.1 : Math.abs(dataMax || dataMin || 1) * 0.01;
  return [dataMin - padding, dataMax + padding];
}

export function AreaTrendChart({
  data,
  currency,
  valueLabel = "Importo",
  format = "currency",
  yAxisDomain = "zero",
}: {
  data: TrendPoint[];
  currency?: string;
  valueLabel?: string;
  format?: "currency" | "percent";
  yAxisDomain?: "zero" | "tight";
}) {
  const theme = useChartTheme();
  const isPercent = format === "percent";
  const formatValue = (value: number) => (isPercent ? formatPercent(value, { signed: true }) : formatMoney(value, currency!));
  const formatAxisValue = (value: number) => (isPercent ? formatPercent(value, { signed: true }) : formatCompactMoney(value, currency!));

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
          tickFormatter={formatAxisValue}
          domain={yAxisDomain === "tight" ? tightDomain(data) : undefined}
        />
        {isPercent && <ReferenceLine y={0} stroke={theme.border} strokeDasharray="3 3" />}
        <Tooltip
          contentStyle={{
            background: theme.surface,
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            color: theme.text,
          }}
          labelStyle={{ color: theme.textMuted }}
          formatter={(value) => [formatValue(Number(value)), valueLabel] as [string, string]}
        />
        <Area type="monotone" dataKey="value" stroke={theme.primary} strokeWidth={2} fill="url(#lumio-area-fill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
