import { useRef, useState } from "react";
import type { PointerEvent } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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

// Margini del grafico: servono a ricavare l'indice del punto dalla posizione
// del dito/mouse (l'area di tracciamento va da `Y_AXIS_WIDTH` a `width - RIGHT`).
const Y_AXIS_WIDTH = 64;
const RIGHT_MARGIN = 8;

export function AreaTrendChart({
  data,
  currency,
  valueLabel = "Importo",
  format = "currency",
  yAxisDomain = "zero",
  onActivePointChange,
}: {
  data: TrendPoint[];
  currency?: string;
  valueLabel?: string;
  format?: "currency" | "percent";
  yAxisDomain?: "zero" | "tight";
  /** Rende il grafico esplorabile (stile Trade Republic): trascinando il dito
   * (o muovendo il mouse) sul grafico il chiamante riceve l'indice del punto
   * sotto il dito, `null` quando si lascia. Il tooltip a riquadro si nasconde:
   * e' l'intestazione della pagina a mostrare valore e data. Lo scorrimento
   * verticale della pagina resta libero (`touch-pan-y`). */
  onActivePointChange?: (index: number | null) => void;
}) {
  const theme = useChartTheme();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const explorable = onActivePointChange !== undefined;
  const isPercent = format === "percent";
  const formatValue = (value: number) => (isPercent ? formatPercent(value, { signed: true }) : formatMoney(value, currency!));
  const formatAxisValue = (value: number) => (isPercent ? formatPercent(value, { signed: true }) : formatCompactMoney(value, currency!));

  const updateActive = (next: number | null) => {
    setActiveIndex(next);
    onActivePointChange?.(next);
  };
  const indexFromPointer = (event: PointerEvent<HTMLDivElement>): number | null => {
    const rect = wrapperRef.current?.getBoundingClientRect();
    if (!rect || data.length === 0) return null;
    const plotWidth = rect.width - Y_AXIS_WIDTH - RIGHT_MARGIN;
    if (plotWidth <= 0) return null;
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left - Y_AXIS_WIDTH) / plotWidth));
    return Math.round(ratio * (data.length - 1));
  };
  const activePoint = activeIndex !== null ? data[activeIndex] : undefined;

  return (
    <div
      ref={wrapperRef}
      className={`h-full w-full ${explorable ? "touch-pan-y select-none" : ""}`}
      onPointerDown={explorable ? (event) => updateActive(indexFromPointer(event)) : undefined}
      onPointerMove={explorable ? (event) => updateActive(indexFromPointer(event)) : undefined}
      onPointerUp={explorable ? () => updateActive(null) : undefined}
      onPointerLeave={explorable ? () => updateActive(null) : undefined}
      onPointerCancel={explorable ? () => updateActive(null) : undefined}
    >
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: RIGHT_MARGIN, left: 0, bottom: 0 }}>
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
          width={Y_AXIS_WIDTH}
          tickFormatter={formatAxisValue}
          domain={yAxisDomain === "tight" ? tightDomain(data) : undefined}
        />
        {isPercent && <ReferenceLine y={0} stroke={theme.border} strokeDasharray="3 3" />}
        {activePoint && (
          <>
            <ReferenceLine x={activePoint.label} stroke={theme.textMuted} strokeWidth={1} />
            <ReferenceDot x={activePoint.label} y={activePoint.value} r={4} fill={theme.primary} stroke={theme.surface} />
          </>
        )}
        {!explorable && (
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
        )}
        <Area type="monotone" dataKey="value" stroke={theme.primary} strokeWidth={2} fill="url(#lumio-area-fill)" />
      </AreaChart>
    </ResponsiveContainer>
    </div>
  );
}
