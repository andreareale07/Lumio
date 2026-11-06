import { HISTORY_PRESETS, type HistoryPreset } from "../../types/api";

/** Preset dell'intervallo di un grafico (1G…Max), discreti come in Trade
 * Republic: solo testo, nessun bordo ne' sfondo, grigio chiaro l'inattivo e
 * scuro con sottolineatura l'attivo. L'area di tocco e' alta 40px anche se
 * non si vede (bersagli di tocco su smartphone). Di default lo storico prezzi
 * di un asset (`HISTORY_PRESETS`); riusato dall'andamento di un portfolio con
 * un insieme di preset eventualmente diverso, da qui il generic.
 * Stato a carico del chiamante (tipicamente `useRangeParam`). */
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
    <div className="-mx-2 flex items-center" role="group" aria-label="Intervallo temporale">
      {presets.map((preset) => {
        const active = preset === value;
        return (
          <button
            key={preset}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(preset)}
            className={`relative h-10 px-2 text-xs transition-colors md:px-2.5 md:text-sm ${
              active
                ? "font-medium text-text after:absolute after:inset-x-2 after:bottom-1.5 after:h-0.5 after:rounded-full after:bg-current md:after:inset-x-2.5"
                : "text-text-muted hover:text-text"
            }`}
          >
            {preset}
          </button>
        );
      })}
    </div>
  );
}
