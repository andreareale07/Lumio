import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { GRANULARITY_ORDER, type Granularity } from "../../lib/period";
import { usePeriodNavigator, type UsePeriodNavigatorOptions } from "../../lib/usePeriodNavigator";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

/** Navigazione temporale condivisa (rework UX/design, slice 1): granularita'
 * + avanti/indietro di un bucket alla volta, con un'opzione "intervallo
 * personalizzato" alternativa. Nessuna prop di stato: legge/scrive gli
 * stessi search param di `usePeriodNavigator`, quindi ogni pagina che lo
 * monta resta sincronizzata automaticamente (stesso principio di
 * `PeriodFilter`, che sostituisce). */
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

  if (mode === "all") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-text">{currentPeriod.label}</span>
        <Button variant="link" size="sm" onClick={() => setGranularity(granularity)}>
          {t("period.filterByPeriod")}
        </Button>
        <Button variant="link" size="sm" onClick={() => setMode("custom")}>
          {t("period.customRange")}
        </Button>
      </div>
    );
  }

  if (mode === "custom") {
    return (
      <div className="flex flex-wrap items-end gap-3">
        <Input
          type="date"
          label={t("period.from")}
          value={customFrom}
          onChange={(e) => setCustomRange(e.target.value, customTo)}
          className="w-auto"
        />
        <Input
          type="date"
          label={t("period.to")}
          value={customTo}
          onChange={(e) => setCustomRange(customFrom, e.target.value)}
          className="w-auto"
        />
        <Button variant="link" size="sm" onClick={() => setMode("granular")}>
          {t("period.backToGranular")}
        </Button>
        {allowAll && (
          <Button variant="link" size="sm" onClick={() => setMode("all")}>
            {t("period.allPeriods")}
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        aria-label={t("period.granularityAriaLabel")}
        value={granularity}
        onChange={(e) => setGranularity(e.target.value as Granularity)}
        className="w-auto"
      >
        {options.map((g) => (
          <option key={g} value={g}>
            {t(`period.granularity.${g}`)}
          </option>
        ))}
      </Select>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon" onClick={goToPrevious} aria-label={t("period.previousAriaLabel")}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="min-w-[8rem] text-center text-sm font-medium text-text">{currentPeriod.label}</span>
        <Button variant="ghost" size="icon" onClick={goToNext} disabled={isAtToday} aria-label={t("period.nextAriaLabel")}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
      {!isAtToday && (
        <Button variant="link" size="sm" onClick={goToToday}>
          {t("period.today")}
        </Button>
      )}
      <Button variant="link" size="sm" onClick={() => setMode("custom")}>
        {t("period.customRange")}
      </Button>
      {allowAll && (
        <Button variant="link" size="sm" onClick={() => setMode("all")}>
          {t("period.allPeriods")}
        </Button>
      )}
    </div>
  );
}
