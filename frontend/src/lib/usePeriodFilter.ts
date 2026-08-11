import { useSearchParams } from "react-router-dom";

import { DEFAULT_PERIOD_PRESET, resolvePeriodPreset, type PeriodPresetKey } from "./period";

/** Stato del filtro periodo in URL search params (come i filtri di
 * `TransactionsPage`, cosi' il periodo e' condivisibile e sopravvive al
 * reload). Piu' hook nella stessa pagina condividono lo stesso periodo
 * perche' leggono gli stessi search params. */
export function usePeriodFilter() {
  const [searchParams, setSearchParams] = useSearchParams();

  const preset = (searchParams.get("period") as PeriodPresetKey | null) ?? DEFAULT_PERIOD_PRESET;
  const customFrom = searchParams.get("from") ?? "";
  const customTo = searchParams.get("to") ?? "";

  const fallback = resolvePeriodPreset(DEFAULT_PERIOD_PRESET)!;
  const resolved =
    preset === "custom"
      ? customFrom && customTo
        ? { date_from: customFrom, date_to: customTo }
        : fallback
      : resolvePeriodPreset(preset) ?? fallback;

  const setPreset = (next: PeriodPresetKey) => {
    const params = new URLSearchParams(searchParams);
    params.set("period", next);
    if (next !== "custom") {
      params.delete("from");
      params.delete("to");
    }
    setSearchParams(params);
  };

  const setCustomRange = (from: string, to: string) => {
    const params = new URLSearchParams(searchParams);
    params.set("period", "custom");
    params.set("from", from);
    params.set("to", to);
    setSearchParams(params);
  };

  return {
    preset,
    customFrom,
    customTo,
    dateFrom: resolved.date_from,
    dateTo: resolved.date_to,
    setPreset,
    setCustomRange,
  };
}
