import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import { usePeriodFilter } from "../../lib/usePeriodFilter";
import { PERIOD_PRESET_LABELS, PERIOD_PRESET_ORDER, type PeriodPresetKey } from "../../lib/period";

/** Filtro periodo globale (SPEC_FE §12.2), condiviso da Dashboard/Spese/
 * Entrate/Patrimonio: legge e scrive gli stessi search param di
 * `usePeriodFilter`, quindi ogni pagina che lo monta e chiama l'hook resta
 * sincronizzata automaticamente. */
export function PeriodFilter() {
  const { preset, customFrom, customTo, setPreset, setCustomRange } = usePeriodFilter();

  return (
    <div className="flex flex-wrap items-end gap-3">
      <Select
        aria-label="Periodo"
        value={preset}
        onChange={(e) => setPreset(e.target.value as PeriodPresetKey)}
        className="w-auto"
      >
        {PERIOD_PRESET_ORDER.map((key) => (
          <option key={key} value={key}>
            {PERIOD_PRESET_LABELS[key]}
          </option>
        ))}
      </Select>
      {preset === "custom" && (
        <>
          <Input
            type="date"
            label="Dal"
            value={customFrom}
            onChange={(e) => setCustomRange(e.target.value, customTo)}
            className="w-auto"
          />
          <Input
            type="date"
            label="Al"
            value={customTo}
            onChange={(e) => setCustomRange(customFrom, e.target.value)}
            className="w-auto"
          />
        </>
      )}
    </div>
  );
}
