import { useId, useRef, useState } from "react";
import { CalendarRange, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { formatDate } from "../../lib/format";
import {
  GRANULARITY_ORDER,
  formatDisplayDate,
  parseDisplayDate,
  periodForAnchor,
  shiftAnchor,
  todayIso,
} from "../../lib/period";
import { useIsDesktop } from "../../lib/useIsDesktop";
import { usePeriodNavigator, type UsePeriodNavigatorOptions } from "../../lib/usePeriodNavigator";
import { BottomSheet } from "../ui/BottomSheet";
import { Button } from "../ui/Button";
import { FloatingPanel } from "../ui/FloatingPanel";
import { RangeCalendar, type DateRangeValue } from "./RangeCalendar";

function DateField({
  label,
  text,
  onTextChange,
  onCommit,
}: {
  label: string;
  text: string;
  onTextChange: (value: string) => void;
  onCommit: () => void;
}) {
  const id = useId();
  return (
    <div className="flex-1">
      <label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </label>
      <input
        id={id}
        type="text"
        inputMode="numeric"
        placeholder="gg/mm/aaaa"
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        onBlur={onCommit}
        onKeyDown={(e) => {
          if (e.key === "Enter") onCommit();
        }}
        className="mt-0.5 h-11 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text md:h-9"
      />
    </div>
  );
}

interface PanelProps {
  initial: DateRangeValue;
  showQuarterShortcuts: boolean;
  months: 1 | 2;
  onApply: (from: string, to: string) => void;
  onQuarter: (offset: 0 | -1) => void;
  onCancel: () => void;
  isQuarterActive: (offset: 0 | -1) => boolean;
  quarterLabel: string;
}

/** Contenuto del pannello calendario: scorciatoie per trimestre, campi
 * digitabili (gg/mm/aaaa, con errori in linea) e calendario a 1 o 2 mesi. */
function PeriodPanel({
  initial,
  showQuarterShortcuts,
  months,
  onApply,
  onQuarter,
  onCancel,
  isQuarterActive,
  quarterLabel,
}: PanelProps) {
  const { t } = useTranslation("common");
  const maxDate = todayIso();
  const [draft, setDraft] = useState<DateRangeValue>(initial);
  const [fromText, setFromText] = useState(formatDisplayDate(initial.from));
  const [toText, setToText] = useState(formatDisplayDate(initial.to));
  const [error, setError] = useState("");

  const setRange = (next: DateRangeValue) => {
    setDraft(next);
    setFromText(formatDisplayDate(next.from));
    setToText(formatDisplayDate(next.to));
    setError("");
  };

  const commit = (field: "from" | "to", text: string) => {
    if (text.trim() === "") {
      setDraft({ ...draft, [field]: "" });
      setError("");
      return;
    }
    const iso = parseDisplayDate(text);
    if (!iso) return setError(t("period.errors.invalidFormat"));
    if (iso > maxDate) return setError(t("period.errors.future"));
    const next = { ...draft, [field]: iso };
    if (next.from && next.to && next.to < next.from) return setError(t("period.errors.endBeforeStart"));
    setRange(next);
  };

  const complete = !!draft.from && !!draft.to;
  const shortcutClass = (active: boolean) =>
    `h-11 rounded-full border px-3 text-sm md:h-8 ${
      active ? "border-primary bg-primary/10 text-primary" : "border-border text-text hover:bg-surface-hover"
    }`;

  return (
    <div className="flex flex-col gap-3 py-2">
      {showQuarterShortcuts && (
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => onQuarter(0)} className={shortcutClass(isQuarterActive(0))}>
            {t("period.shortcuts.currentQuarter", { label: quarterLabel })}
          </button>
          <button type="button" onClick={() => onQuarter(-1)} className={shortcutClass(isQuarterActive(-1))}>
            {t("period.shortcuts.previousQuarter")}
          </button>
        </div>
      )}

      <div className="flex gap-2">
        <DateField label={t("period.from")} text={fromText} onTextChange={setFromText} onCommit={() => commit("from", fromText)} />
        <DateField label={t("period.to")} text={toText} onTextChange={setToText} onCommit={() => commit("to", toText)} />
      </div>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}

      <RangeCalendar value={draft} onChange={setRange} months={months} maxDate={maxDate} />

      <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
        <span className="text-xs text-text-muted" aria-live="polite">
          {complete ? `${formatDate(draft.from)} – ${formatDate(draft.to)}` : t("period.calendar.pickTwo")}
        </span>
        <span className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} className="h-11 md:h-8">
            {t("actions.cancel")}
          </Button>
          <Button size="sm" disabled={!complete} onClick={() => onApply(draft.from, draft.to)} className="h-11 md:h-8">
            {t("period.apply")}
          </Button>
        </span>
      </div>
    </div>
  );
}

/** Selettore di periodo condiviso (revisione globale di filtri e periodo,
 * 2026-11-06). Le scelte comuni sono sempre a vista come semplice testo —
 * Mese, Anno, 3M, 12M e, dove serve, Tutto — piu' l'icona del calendario, che
 * apre un pannello con le scorciatoie per trimestre, le date digitabili e il
 * calendario (bottom sheet su smartphone, popover su desktop). Sotto, le frecce
 * ‹ etichetta › scorrono il periodo (solo per mese/anno/trimestre...). Il
 * periodo attivo e' sempre scritto in chiaro con le date esatte. Giorno,
 * settimana e semestre non si offrono piu' nell'interfaccia (l'URL li accetta
 * ancora, per i link esistenti). Stato nell'URL (`usePeriodNavigator`). */
export function PeriodNavigator({ granularities, trendWindowSize, allowAll, family }: UsePeriodNavigatorOptions) {
  const { t } = useTranslation("common");
  const {
    mode,
    granularity,
    currentPeriod,
    isAtToday,
    customFrom,
    customTo,
    rolling,
    selectGranularity,
    selectBucket,
    setRolling,
    goToPrevious,
    goToNext,
    setMode,
    setCustomRange,
  } = usePeriodNavigator({ granularities, trendWindowSize, allowAll, family });

  const isDesktop = useIsDesktop();
  const [panelOpen, setPanelOpen] = useState(false);
  const calendarButtonRef = useRef<HTMLButtonElement>(null);
  const closePanel = () => setPanelOpen(false);

  const allowed = granularities ?? GRANULARITY_ORDER;
  const canStep = mode === "granular";
  const quarterAllowed = allowed.includes("quarter");

  const pills: { key: string; label: string; active: boolean; onClick: () => void }[] = [];
  if (allowed.includes("month"))
    pills.push({
      key: "month",
      label: t("period.pills.month"),
      active: mode === "granular" && granularity === "month",
      onClick: () => selectGranularity("month"),
    });
  if (allowed.includes("year"))
    pills.push({
      key: "year",
      label: t("period.pills.year"),
      active: mode === "granular" && granularity === "year",
      onClick: () => selectGranularity("year"),
    });
  pills.push(
    { key: "3m", label: t("period.pills.3m"), active: rolling === "3m", onClick: () => setRolling("3m") },
    { key: "12m", label: t("period.pills.12m"), active: rolling === "12m", onClick: () => setRolling("12m") },
  );
  if (allowAll) pills.push({ key: "all", label: t("period.pills.all"), active: mode === "all", onClick: () => setMode("all") });

  const calendarActive = mode === "custom" || (mode === "granular" && granularity !== "month" && granularity !== "year");

  const label =
    mode === "custom" && customFrom && customTo ? `${formatDate(customFrom)} – ${formatDate(customTo)}` : currentPeriod.label;
  // Per l'intervallo personalizzato l'etichetta e' gia' l'intervallo: niente riga doppia.
  const span =
    mode === "all"
      ? t("period.allSpan")
      : mode === "custom"
        ? ""
        : currentPeriod.date_from && currentPeriod.date_to
          ? `${formatDate(currentPeriod.date_from)} – ${formatDate(currentPeriod.date_to)}`
          : "";

  const quarterRange = (offset: 0 | -1) => periodForAnchor("quarter", shiftAnchor("quarter", new Date(), offset));
  const currentQuarterLabel = (() => {
    const start = new Date(`${quarterRange(0).date_from}T00:00:00`);
    return `${t("period.quarterAbbrev")}${Math.floor(start.getMonth() / 3) + 1} ${start.getFullYear()}`;
  })();
  const isQuarterActive = (offset: 0 | -1) =>
    mode === "granular" && granularity === "quarter" && currentPeriod.date_from === quarterRange(offset).date_from;

  const onQuarter = (offset: 0 | -1) => {
    selectBucket("quarter", shiftAnchor("quarter", new Date(), offset));
    closePanel();
  };

  const initialRange: DateRangeValue =
    mode === "custom" && customFrom && customTo ? { from: customFrom, to: customTo } : { from: "", to: "" };

  const pillClass = (active: boolean) =>
    `relative h-11 px-3 text-sm md:h-9 ${
      active ? "font-medium text-text after:absolute after:inset-x-3 after:bottom-2 after:h-0.5 after:rounded-full after:bg-current" : "text-text-muted hover:text-text"
    }`;

  const panel = (
    <PeriodPanel
      initial={initialRange}
      showQuarterShortcuts={quarterAllowed}
      months={isDesktop ? 2 : 1}
      onApply={(from, to) => {
        setCustomRange(from, to);
        closePanel();
      }}
      onQuarter={onQuarter}
      onCancel={closePanel}
      isQuarterActive={isQuarterActive}
      quarterLabel={currentQuarterLabel}
    />
  );

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-x-1 gap-y-0 md:gap-x-3">
        <div className="-mx-3 flex items-center" role="group" aria-label={t("period.filterByPeriod")}>
          {pills.map((pill) => (
            <button key={pill.key} type="button" aria-pressed={pill.active} onClick={pill.onClick} className={pillClass(pill.active)}>
              {pill.label}
            </button>
          ))}
          <button
            ref={calendarButtonRef}
            type="button"
            onClick={() => setPanelOpen((open) => !open)}
            aria-label={t("period.customRange")}
            aria-pressed={calendarActive}
            aria-haspopup="dialog"
            aria-expanded={panelOpen}
            className={`flex h-11 w-11 items-center justify-center md:h-9 md:w-9 ${
              calendarActive ? "text-primary" : "text-text-muted hover:text-text"
            }`}
          >
            <CalendarRange className="h-4 w-4" />
          </button>
        </div>

        <div className="-ml-2 flex items-center md:ml-0">
          <Button
            variant="ghost"
            size="icon"
            onClick={goToPrevious}
            disabled={!canStep}
            aria-label={t("period.previousAriaLabel")}
            className="h-11 w-11 md:h-8 md:w-8"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[9rem] px-1 text-center text-sm font-medium text-text">{label}</span>
          <Button
            variant="ghost"
            size="icon"
            onClick={goToNext}
            disabled={!canStep || isAtToday}
            aria-label={t("period.nextAriaLabel")}
            className="h-11 w-11 md:h-8 md:w-8"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {span && <p className="text-xs text-text-muted">{span}</p>}

      {isDesktop ? (
        <FloatingPanel open={panelOpen} anchorRef={calendarButtonRef} onClose={closePanel} align="end">
          <div className="w-[34rem] max-w-[calc(100vw-2rem)] px-4 py-2">{panel}</div>
        </FloatingPanel>
      ) : (
        <BottomSheet open={panelOpen} onClose={closePanel} title={t("period.calendar.title")}>
          {panel}
        </BottomSheet>
      )}
    </div>
  );
}
