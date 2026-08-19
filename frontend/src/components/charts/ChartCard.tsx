import type { ReactNode } from "react";

import { Card } from "../ui/Card";

interface ChartCardProps {
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  /** Alternativa testuale/tabellare del grafico (SPEC_FE §59): sempre
   * presente nel DOM (accessibile via screen reader e query Playwright),
   * visivamente nascosta perche' il grafico stesso e' la presentazione
   * primaria per chi vede lo schermo. */
  tableCaption: string;
  tableHeaders: string[];
  tableRows: (string | number)[][];
  children: ReactNode;
  empty?: boolean;
  emptyState?: ReactNode;
  /** `false` dove una legenda GIA' VISIBILE (es. `DonutChart legend="side"`)
   * elenca le stesse righe: evita di far leggere due volte la stessa
   * informazione a chi usa uno screen reader. Default `true` (comportamento
   * invariato per ogni chiamante esistente). */
  dataTable?: boolean;
  /** Altezza del box che contiene il grafico (default `"h-64"`, invariato).
   * Un donut con legenda "bottom"/"side" (`DonutChart`) ha bisogno di piu'
   * spazio verticale del solo cerchio. */
  chartClassName?: string;
  /** Contenuto libero sotto il grafico (es. "Inizio · Fine · Variazione"
   * per un'area chart) — dare uno scopo dichiarato al grafico invece di
   * lasciare all'utente il compito di leggerlo a occhio. */
  footer?: ReactNode;
}

export function ChartCard({
  title,
  subtitle,
  action,
  tableCaption,
  tableHeaders,
  tableRows,
  children,
  empty,
  emptyState,
  dataTable = true,
  chartClassName = "h-64",
  footer,
}: ChartCardProps) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-text">{title}</h3>
          {subtitle && <div className="text-sm text-text-muted">{subtitle}</div>}
        </div>
        {action}
      </div>

      {empty ? (
        emptyState
      ) : (
        <>
          <div className={`${chartClassName} w-full overflow-hidden`}>{children}</div>
          {footer}
          {dataTable && (
            <table className="sr-only">
              <caption>{tableCaption}</caption>
              <thead>
                <tr>
                  {tableHeaders.map((header) => (
                    <th key={header}>{header}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </Card>
  );
}
