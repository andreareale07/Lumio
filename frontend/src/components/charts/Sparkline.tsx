import { useId } from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";

import { useChartTheme } from "./chartTheme";

/** Trend minimale per una KPI card (SPEC_FE §13: "ogni KPI card ha un mini
 * chart") — deliberatamente senza assi/griglia/tooltip/legenda: e' un
 * indicatore d'insieme ("sta salendo o scendendo?"), non un grafico da
 * leggere in dettaglio — quello e' il compito del grafico grande sotto,
 * o del drill-down. Nessuna interattivita' per design (convenzione
 * standard per uno sparkline). */
export function Sparkline({ values, tone = "primary" }: { values: number[]; tone?: "primary" | "success" | "danger" }) {
  const theme = useChartTheme();
  // Id univoco per istanza: piu' sparkline della stessa tonalita' nella
  // stessa pagina non devono condividere un id di gradiente SVG (invalido
  // quando compaiono piu' `<svg>` nello stesso documento).
  const gradientId = `sparkline-fill-${useId()}`;
  if (values.length < 2) return null;

  const color = tone === "success" ? theme.success : tone === "danger" ? theme.danger : theme.primary;
  const data = values.map((value, i) => ({ i, value }));

  return (
    <div className="h-8 w-20">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
