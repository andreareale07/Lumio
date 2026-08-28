import { useId, useRef, useState } from "react";
import { CalendarRange, Check, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { formatDate } from "../../lib/format";
import { GRANULARITY_ORDER, type Granularity } from "../../lib/period";
import { usePeriodNavigator, type UsePeriodNavigatorOptions } from "../../lib/usePeriodNavigator";
import { Button } from "../ui/Button";
import { FloatingPanel } from "../ui/FloatingPanel";

/** Campo data compatto (etichetta ACCANTO, non sopra) — a differenza di
 * `Input.tsx` (label sempre impilata sopra), qui serve stare su una sola
 * riga dentro il pannello dell'intervallo personalizzato. */
function CompactDateField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-2">
      <label htmlFor={id} className="shrink-0 text-sm text-text-muted">
        {label}
      </label>
      <input
        id={id}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-auto rounded-lg border border-border bg-surface px-2 text-sm text-text"
      />
    </div>
  );
}

/** Navigazione temporale condivisa (FETTA 0 del redesign Spese/Entrate/
 * Dashboard, sostituisce la versione a tre pezzi con `<Select>` nativo):
 * un unico blocco piatto — `‹` `etichetta ▾` `›` — senza contorno/sfondo a
 * riposo, deciso con l'utente via mockup interattivi prima del codice.
 * L'etichetta centrale E' il selettore di granularita': un click apre un
 * piccolo menu (Mese/Trimestre/Anno/... + "Max" quando `allowAll`), non
 * piu' un `<select>` nativo. L'icona calendario apre un pannello flottante
 * per l'intervallo personalizzato SENZA sostituire il resto del controllo
 * (prima lo rimpiazzava del tutto).
 *
 * Entrambi i popover usano `FloatingPanel` (portal + `position: fixed`),
 * non un semplice `absolute` come in `Combobox.tsx`: montato nel Topbar
 * (`usePageToolbar`), il cui slot ha `overflow-x-auto` — bug reale trovato
 * dall'utente, `overflow-x` costringe anche `overflow-y` a `auto` per la
 * spec CSS, quindi un popover `absolute` restava tagliato dentro lo slot
 * con una scrollbar invece di fluttuare sopra la pagina. */
export function PeriodNavigator({ granularities, trendWindowSize, allowAll }: UsePeriodNavigatorOptions) {
  const { t } = useTranslation("common");
  const {
    mode,
    granularity,
    currentPeriod,
    isAtToday,
    customFrom,
    customTo,
    setGranularity,
    goToPrevious,
    goToNext,
    goToToday,
    setMode,
    setCustomRange,
  } = usePeriodNavigator({ granularities, trendWindowSize, allowAll });

  const options = granularities ?? GRANULARITY_ORDER;

  const [menuOpen, setMenuOpen] = useState(false);
  const menuTriggerRef = useRef<HTMLButtonElement>(null);

  const [rangeOpen, setRangeOpen] = useState(false);
  const rangeTriggerRef = useRef<HTMLButtonElement>(null);
  const [draftFrom, setDraftFrom] = useState(customFrom);
  const [draftTo, setDraftTo] = useState(customTo);

  function openRangePanel() {
    setDraftFrom(customFrom);
    setDraftTo(customTo);
    setRangeOpen(true);
    setMenuOpen(false);
  }

  function applyRange() {
    if (draftFrom && draftTo) setCustomRange(draftFrom, draftTo);
    setRangeOpen(false);
  }

  function selectGranularity(next: Granularity) {
    setGranularity(next);
    setMenuOpen(false);
  }

  function selectAll() {
    setMode("all");
    setMenuOpen(false);
  }

  // In modalita' custom l'etichetta generica dell'hook ("Intervallo
  // personalizzato") diventa qui il range vero e proprio — piu' utile nel
  // trigger del menu, dove lo spazio per un'etichetta descrittiva c'e' gia'.
  const triggerLabel =
    mode === "custom" && customFrom && customTo ? `${formatDate(customFrom)} – ${formatDate(customTo)}` : currentPeriod.label;

  return (
    <div className="flex flex-wrap items-center gap-1">
      <Button variant="ghost" size="icon" onClick={goToPrevious} aria-label={t("period.previousAriaLabel")}>
        <ChevronLeft className="h-4 w-4" />
      </Button>

      <Button
        ref={menuTriggerRef}
        variant="ghost"
        size="sm"
        onClick={() => setMenuOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
      >
        <span className="min-w-[8rem] text-center">{triggerLabel}</span>
        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
      <FloatingPanel open={menuOpen} anchorRef={menuTriggerRef} onClose={() => setMenuOpen(false)} align="center">
        <div role="menu" aria-label={t("period.granularityAriaLabel")} className="w-40 p-1">
          {options.map((g) => {
            const selected = mode === "granular" && granularity === g;
            return (
              <button
                key={g}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                onClick={() => selectGranularity(g)}
                className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-hover ${
                  selected ? "font-medium text-text" : "text-text-muted"
                }`}
              >
                {t(`period.granularity.${g}`)}
                {selected && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
              </button>
            );
          })}
          {allowAll && (
            <button
              type="button"
              role="menuitemradio"
              aria-checked={mode === "all"}
              onClick={selectAll}
              className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-hover ${
                mode === "all" ? "font-medium text-text" : "text-text-muted"
              }`}
            >
              {t("period.allPeriods")}
              {mode === "all" && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
            </button>
          )}
        </div>
      </FloatingPanel>

      <Button variant="ghost" size="icon" onClick={goToNext} disabled={isAtToday} aria-label={t("period.nextAriaLabel")}>
        <ChevronRight className="h-4 w-4" />
      </Button>

      {!isAtToday && (
        <Button variant="link" size="sm" onClick={goToToday}>
          {t("period.today")}
        </Button>
      )}

      <Button
        ref={rangeTriggerRef}
        variant="ghost"
        size="icon"
        onClick={() => (rangeOpen ? setRangeOpen(false) : openRangePanel())}
        aria-label={t("period.customRange")}
        aria-pressed={mode === "custom"}
      >
        <CalendarRange className="h-4 w-4" />
      </Button>
      <FloatingPanel open={rangeOpen} anchorRef={rangeTriggerRef} onClose={() => setRangeOpen(false)} align="end">
        <div className="w-64 p-3">
          <p className="mb-2 text-xs font-medium text-text-muted">{t("period.customRange")}</p>
          <div className="flex flex-col gap-2">
            <CompactDateField label={t("period.from")} value={draftFrom} onChange={setDraftFrom} />
            <CompactDateField label={t("period.to")} value={draftTo} onChange={setDraftTo} />
            <Button variant="secondary" size="sm" onClick={applyRange} disabled={!draftFrom || !draftTo}>
              {t("period.apply")}
            </Button>
          </div>
        </div>
      </FloatingPanel>
    </div>
  );
}
