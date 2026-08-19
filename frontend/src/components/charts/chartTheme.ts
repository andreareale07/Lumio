import { useEffect, useState } from "react";

export interface ChartTheme {
  text: string;
  textMuted: string;
  border: string;
  surface: string;
  primary: string;
  success: string;
  danger: string;
  warning: string;
  categorical: string[];
}

function readVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function readTheme(): ChartTheme {
  return {
    text: readVar("--color-text"),
    textMuted: readVar("--color-text-muted"),
    border: readVar("--color-border"),
    surface: readVar("--color-surface"),
    primary: readVar("--color-primary"),
    success: readVar("--color-success"),
    danger: readVar("--color-danger"),
    warning: readVar("--color-warning"),
    categorical: [1, 2, 3, 4, 5, 6].map((n) => readVar(`--color-chart-${n}`)),
  };
}

/** I colori dei token vivono come CSS custom properties e il tema cambia a
 * runtime senza remount (`data-theme` sull'`<html>`, o la preferenza di
 * sistema via `@media`) — Recharts vuole colori concreti, quindi questo
 * hook li ri-legge quando il tema cambia in uno dei due modi. */
export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState<ChartTheme>(readTheme);

  useEffect(() => {
    const update = () => setTheme(readTheme());

    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", update);

    return () => {
      observer.disconnect();
      media.removeEventListener("change", update);
    };
  }, []);

  return theme;
}

/** Unico punto che sceglie il colore categorico N — usato SIA dalle fette
 * del donut SIA dagli swatch della sua legenda (`ChartLegend`), cosi' i
 * due non possono mai divergere (prima la formula `theme.categorical[i %
 * len]` era duplicata inline in ogni chiamante). */
export function categoricalColor(theme: ChartTheme, index: number): string {
  return theme.categorical[index % theme.categorical.length];
}
