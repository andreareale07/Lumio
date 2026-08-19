import { HISTORY_PRESETS, type HistoryPreset } from "../../types/api";

/** Riga di pulsanti 1G/1S/.../Max — di default lo storico prezzi asset
 * (`HISTORY_PRESETS`), ma riusata anche per l'andamento di un portfolio
 * (`PortfolioSummaryBlock`) con un sottoinsieme diverso di preset (`1G`/`1S`
 * non hanno senso per un aggregato multi-asset senza quotazioni intraday):
 * da qui il generic, cosi' entrambi i chiamanti restano lo stesso
 * componente invece di due implementazioni parallele. Non basato su
 * `usePeriodNavigator` (modello granularita'+ancora, non esprime bene "5A"
 * o "Max" — vedi piano Step 2): stato locale semplice, un preset alla
 * volta. */
export function RangeSelector<P extends string = HistoryPreset>({
  value,
  onChange,
  presets = HISTORY_PRESETS as unknown as readonly P[],
}: {
  value: P;
  onChange: (preset: P) => void;
  presets?: readonly P[];
}) {
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Intervallo temporale">
      {presets.map((preset) => (
        <button
          key={preset}
          type="button"
          aria-pressed={preset === value}
          onClick={() => onChange(preset)}
          className={`rounded-md px-2.5 py-1 text-sm font-medium transition-colors ${
            preset === value
              ? "bg-primary text-primary-contrast"
              : "text-text-muted hover:bg-surface-hover hover:text-text"
          }`}
        >
          {preset}
        </button>
      ))}
    </div>
  );
}
