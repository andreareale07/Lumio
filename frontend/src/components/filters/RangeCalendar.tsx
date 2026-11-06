import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { formatDate, intlLocale } from "../../lib/format";

export interface DateRangeValue {
  from: string;
  to: string;
}

interface RangeCalendarProps {
  value: DateRangeValue;
  onChange: (next: DateRangeValue) => void;
  /** 1 mese su smartphone, 2 su desktop. */
  months: 1 | 2;
  /** ISO: le date successive non sono selezionabili. */
  maxDate: string;
}

function toIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function MonthGrid({
  year,
  month,
  value,
  maxDate,
  onPick,
}: {
  year: number;
  month: number;
  value: DateRangeValue;
  maxDate: string;
  onPick: (iso: string) => void;
}) {
  const locale = intlLocale();
  // Lunedi' come primo giorno (convenzione italiana, stessa di `bucketStart`).
  const weekdays = Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(locale, { weekday: "narrow" }).format(new Date(2024, 0, 1 + i)),
  );
  const offset = (new Date(year, month, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  return (
    <div className="grid grid-cols-7 gap-0.5 text-center">
      {weekdays.map((label, i) => (
        <span key={i} className="py-1 text-xs text-text-muted" aria-hidden="true">
          {label}
        </span>
      ))}
      {Array.from({ length: offset }, (_, i) => (
        <span key={`pad-${i}`} />
      ))}
      {Array.from({ length: daysInMonth }, (_, i) => {
        const iso = toIso(new Date(year, month, i + 1));
        const isEnd = iso === value.from || iso === value.to;
        const inRange = !!value.from && !!value.to && iso > value.from && iso < value.to;
        const disabled = iso > maxDate;
        return (
          <button
            key={iso}
            type="button"
            disabled={disabled}
            onClick={() => onPick(iso)}
            aria-label={formatDate(iso)}
            aria-pressed={isEnd}
            className={`h-9 text-sm disabled:cursor-not-allowed disabled:opacity-30 md:h-8 ${
              isEnd
                ? "rounded-md bg-primary font-medium text-primary-contrast underline"
                : inRange
                  ? "bg-primary/10 text-text"
                  : "rounded-md text-text hover:bg-surface-hover"
            }`}
          >
            {i + 1}
          </button>
        );
      })}
    </div>
  );
}

/** Calendario per scegliere un intervallo con due tocchi: il primo imposta
 * l'inizio, il secondo la fine (un secondo tocco prima dell'inizio riparte da
 * quella data). Inizio e fine sono marcati con sfondo pieno + sottolineatura,
 * non solo col colore. Il calendario non e' l'unico modo di inserire le date:
 * il pannello che lo ospita ha anche i campi digitabili. */
export function RangeCalendar({ value, onChange, months, maxDate }: RangeCalendarProps) {
  const { t } = useTranslation("common");
  const maxMonth = new Date(`${maxDate}T00:00:00`);
  const [view, setView] = useState(() => {
    const base = value.to || value.from || maxDate;
    const d = new Date(`${base}T00:00:00`);
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });

  const pick = (iso: string) => {
    if (!value.from || value.to || iso < value.from) onChange({ from: iso, to: "" });
    else onChange({ from: value.from, to: iso });
  };

  const monthDates = Array.from({ length: months }, (_, i) => new Date(view.getFullYear(), view.getMonth() - (months - 1) + i, 1));
  const atLastMonth = view.getFullYear() === maxMonth.getFullYear() && view.getMonth() >= maxMonth.getMonth();
  const monthFormat = new Intl.DateTimeFormat(intlLocale(), { month: "long", year: "numeric" });

  return (
    <div className="flex items-start gap-4">
      {monthDates.map((d, index) => (
        <div key={d.toISOString()} className="min-w-0 flex-1">
          <div className="mb-1 flex items-center justify-between">
            {index === 0 ? (
              <button
                type="button"
                onClick={() => setView(new Date(view.getFullYear(), view.getMonth() - 1, 1))}
                aria-label={t("period.calendar.previousMonth")}
                className="flex h-11 w-11 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover md:h-8 md:w-8"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            ) : (
              <span className="h-11 w-11 md:h-8 md:w-8" />
            )}
            <span className="text-sm font-medium capitalize text-text">{monthFormat.format(d)}</span>
            {index === monthDates.length - 1 ? (
              <button
                type="button"
                onClick={() => setView(new Date(view.getFullYear(), view.getMonth() + 1, 1))}
                disabled={atLastMonth}
                aria-label={t("period.calendar.nextMonth")}
                className="flex h-11 w-11 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover disabled:opacity-30 md:h-8 md:w-8"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            ) : (
              <span className="h-11 w-11 md:h-8 md:w-8" />
            )}
          </div>
          <MonthGrid year={d.getFullYear()} month={d.getMonth()} value={value} maxDate={maxDate} onPick={pick} />
        </div>
      ))}
    </div>
  );
}
