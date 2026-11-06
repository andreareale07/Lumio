import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { intlLocale } from "./format";
import {
  DEFAULT_GRANULARITY,
  GRANULARITY_ORDER,
  type Granularity,
  type Period,
  migrateLegacyPeriodParams,
  periodForAnchor,
  periodLabel,
  resolveRolling,
  ROLLING_PRESETS,
  type RollingPreset,
  shiftAnchor,
  slidingWindow,
} from "./period";

export type PeriodMode = "all" | "granular" | "custom" | "rolling";

export interface UsePeriodNavigatorOptions {
  /** Granularita' offerte da questa pagina — di default tutte. Il valore
   * effettivo puo' comunque restare fuori da questo elenco se l'URL lo
   * imposta esplicitamente (nessun clamp forzato, solo il fallback quando
   * non c'e' ancora nulla nell'URL). */
  granularities?: Granularity[];
  /** Numero di bucket della finestra scorrevole usata per i grafici trend
   * (`trendWindow`) — il periodo puntuale (`currentPeriod`) resta sempre un
   * singolo bucket, indipendentemente da questo valore. */
  trendWindowSize?: number;
  /** Abilita la modalita' "tutti i periodi" (nessun filtro data) come
   * default quando l'URL non ha ancora nessuno stato — pensata per le
   * pagine di consultazione/ricerca (es. Transazioni) dove nascondere dati
   * fuori da "questo mese" per default sarebbe una sorpresa pericolosa
   * (es. un import appena fatto con date diverse spariva dalla lista). Le
   * pagine di riepilogo (Dashboard/Analytics/Performance) NON la abilitano:
   * per loro "questo mese" e' il default corretto. */
  allowAll?: boolean;
  /** Famiglia di pagine che condividono il periodo (es. "analysis": Panoramica,
   * Spese, Entrate, Patrimonio). Aprendo una pagina della famiglia senza stato
   * nell'URL si riparte dall'ultimo periodo scelto in quella famiglia (salvato
   * in sessionStorage); l'URL resta la fonte di verita', quindi i link con
   * periodo esplicito (drill-down) vincono sempre. Senza `family` ogni pagina
   * riparte dal proprio default. */
  family?: string;
}

export interface PeriodNavigatorState {
  mode: PeriodMode;
  granularity: Granularity;
  /** Periodo del bucket corrente — usato per KPI/breakdown puntuali. In
   * modalita' "custom" e' semplicemente il range scelto dall'utente. */
  currentPeriod: Period & { label: string };
  /** Finestra di N bucket che termina nel bucket corrente — usata dai
   * grafici trend multi-periodo (stesso controllo di navigazione, decisione
   * presa con l'utente: "la finestra scorre insieme" al periodo puntuale).
   * In modalita' "custom" coincide con `currentPeriod`. */
  trendWindow: Period;
  /** true quando il bucket corrente e' oggi (o successivo, per eccesso di
   * navigazione) — usato per disabilitare la freccia "avanti". */
  isAtToday: boolean;
  /** Data di ancoraggio del bucket corrente (redesign Spese/Entrate, FETTA
   * 1) — esposta cosi' una pagina puo' calcolare una finestra trend diversa
   * da `trendWindow` (es. una finestra dimensionata ad hoc per il confronto
   * anno-su-anno) senza duplicare la logica di parsing di `anchor` dall'URL. */
  anchor: Date;
  customFrom: string;
  customTo: string;
  /** Finestra mobile attiva (3M/12M) quando `mode === "rolling"`. */
  rolling: RollingPreset | null;
  setGranularity: (granularity: Granularity) => void;
  /** Passa a `granularity` posizionandosi sul bucket corrente (oggi), a
   * differenza di `setGranularity` che conserva l'ancora attuale. */
  selectGranularity: (granularity: Granularity) => void;
  /** Passa a `granularity` posizionandosi sul bucket che contiene `date`. */
  selectBucket: (granularity: Granularity, date: Date) => void;
  setRolling: (preset: RollingPreset) => void;
  goToPrevious: () => void;
  goToNext: () => void;
  goToToday: () => void;
  setMode: (mode: PeriodMode) => void;
  setCustomRange: (from: string, to: string) => void;
}

const NEW_STATE_KEYS = ["mode", "granularity", "anchor", "from", "to", "rolling"];

function storageKey(family: string): string {
  return `lumio.period.${family}`;
}

function readStoredPeriod(family: string | undefined): URLSearchParams | null {
  if (!family) return null;
  try {
    const raw = sessionStorage.getItem(storageKey(family));
    return raw ? new URLSearchParams(raw) : null;
  } catch {
    return null;
  }
}

function writeStoredPeriod(family: string, params: URLSearchParams): void {
  const subset = new URLSearchParams();
  for (const key of NEW_STATE_KEYS) {
    const value = params.get(key);
    if (value !== null) subset.set(key, value);
  }
  try {
    sessionStorage.setItem(storageKey(family), subset.toString());
  } catch {
    /* storage non disponibile (finestra privata, quota): si perde solo la memoria */
  }
}

/** Navigazione temporale condivisa (rework UX/design, slice 1): granularita'
 * (giorno/settimana/mese/trimestre/semestre/anno) + avanti/indietro di un
 * bucket alla volta, con una modalita' "intervallo personalizzato"
 * alternativa. Stato in URL search params, stesso principio di
 * `usePeriodFilter` (piu' hook nella stessa pagina restano sincronizzati
 * perche' leggono gli stessi search params) — non lo estende in-place per
 * permettere alle pagine non ancora migrate di continuare a funzionare
 * durante il rollout incrementale. */
export function usePeriodNavigator(options: UsePeriodNavigatorOptions = {}): PeriodNavigatorState {
  const { t } = useTranslation("common");
  const allowedGranularities = options.granularities ?? GRANULARITY_ORDER;
  const trendWindowSize = options.trendWindowSize ?? 6;
  const fallbackGranularity = allowedGranularities.includes(DEFAULT_GRANULARITY)
    ? DEFAULT_GRANULARITY
    : allowedGranularities[0];

  const [searchParams, setSearchParams] = useSearchParams();
  const hasNewState = NEW_STATE_KEYS.some((key) => searchParams.has(key));
  // Stato della famiglia da ripristinare: solo se l'URL non ha nulla (ne' stato
  // nuovo ne' un vecchio ?period= da migrare).
  const storedParams = !hasNewState && !searchParams.has("period") ? readStoredPeriod(options.family) : null;
  const effective = storedParams ?? searchParams;
  const hasState = hasNewState || storedParams !== null;

  // Ripristino del periodo della famiglia: si scrive nell'URL (replace) cosi'
  // resta condivisibile e coerente con il resto dell'app.
  useEffect(() => {
    if (!storedParams) return;
    const next = new URLSearchParams(searchParams);
    for (const key of NEW_STATE_KEYS) {
      const value = storedParams.get(key);
      if (value !== null) next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  }, [storedParams, searchParams, setSearchParams]);

  const family = options.family;
  const searchKey = searchParams.toString();
  useEffect(() => {
    if (family && hasNewState) writeStoredPeriod(family, new URLSearchParams(searchKey));
  }, [family, hasNewState, searchKey]);

  // Migrazione one-shot da un vecchio `?period=<preset>` (mai eseguita se lo
  // stato nuovo e' gia' nell'URL) — MAI durante il render: setSearchParams
  // e' una navigazione, non un aggiornamento di stato locale.
  useEffect(() => {
    if (hasNewState) return;
    const migrated = migrateLegacyPeriodParams(searchParams);
    if (!migrated) return;
    const next = new URLSearchParams(searchParams);
    next.delete("period");
    if (migrated.mode === "custom") {
      next.set("mode", "custom");
      next.set("from", migrated.from);
      next.set("to", migrated.to);
    } else {
      next.set("mode", "granular");
      next.set("granularity", migrated.granularity);
      next.set("anchor", migrated.anchor);
    }
    setSearchParams(next, { replace: true });
  }, [hasNewState, searchParams, setSearchParams]);

  // L'effect sopra e' asincrono rispetto al render: si calcola comunque la
  // migrazione anche qui, per non mostrare per un frame i valori di default
  // invece di quelli migrati.
  const migratedForThisRender = hasNewState ? null : migrateLegacyPeriodParams(searchParams);

  const granularity =
    (effective.get("granularity") as Granularity | null) ??
    (migratedForThisRender?.mode === "granular" ? migratedForThisRender.granularity : null) ??
    fallbackGranularity;

  const urlMode = effective.get("mode");
  const rollingParam = effective.get("rolling") as RollingPreset | null;
  const rolling: RollingPreset | null =
    urlMode === "rolling" ? (rollingParam && ROLLING_PRESETS.includes(rollingParam) ? rollingParam : "3m") : null;
  const mode: PeriodMode =
    rolling !== null
      ? "rolling"
      : urlMode === "custom" || migratedForThisRender?.mode === "custom"
        ? "custom"
        : urlMode === "all" || (options.allowAll && !hasState && !migratedForThisRender)
          ? "all"
          : "granular";

  const anchorIso =
    effective.get("anchor") ??
    (migratedForThisRender?.mode === "granular" ? migratedForThisRender.anchor : null) ??
    periodForAnchor(granularity, new Date()).date_from;
  const anchor = new Date(`${anchorIso}T00:00:00`);

  const customFrom =
    effective.get("from") ?? (migratedForThisRender?.mode === "custom" ? migratedForThisRender.from : "");
  const customTo =
    effective.get("to") ?? (migratedForThisRender?.mode === "custom" ? migratedForThisRender.to : "");

  const currentBucket = periodForAnchor(granularity, anchor);
  const currentPeriod: Period & { label: string } =
    mode === "all"
      ? { date_from: "", date_to: "", label: t("period.allPeriods") }
      : mode === "rolling" && rolling
        ? { ...resolveRolling(rolling), label: t(`period.rolling.${rolling}`) }
        : mode === "custom" && customFrom && customTo
        ? { date_from: customFrom, date_to: customTo, label: t("period.customRange") }
        : {
            ...currentBucket,
            label: periodLabel(granularity, anchor, {
              locale: intlLocale(),
              quarterAbbrev: t("period.quarterAbbrev"),
              semesterAbbrev: t("period.semesterAbbrev"),
              weekLabel: (date) => t("period.weekLabel", { date }),
            }),
          };

  const trendWindow: Period =
    mode === "all"
      ? { date_from: "", date_to: "" }
      : mode === "rolling" && rolling
        ? resolveRolling(rolling)
        : mode === "custom" && customFrom && customTo
        ? { date_from: customFrom, date_to: customTo }
        : slidingWindow(granularity, anchor, trendWindowSize);

  const todayBucketStart = periodForAnchor(granularity, new Date()).date_from;
  const isAtToday = mode === "all" || mode === "rolling" ? true : currentBucket.date_from >= todayBucketStart;

  function updateParams(mutate: (params: URLSearchParams) => void) {
    const next = new URLSearchParams(searchParams);
    mutate(next);
    setSearchParams(next);
  }

  function setGranularityAndAnchor(params: URLSearchParams, nextGranularity: Granularity, nextAnchor: Date) {
    params.set("mode", "granular");
    params.set("granularity", nextGranularity);
    params.set("anchor", periodForAnchor(nextGranularity, nextAnchor).date_from);
    params.delete("from");
    params.delete("to");
    params.delete("rolling");
  }

  return {
    mode,
    granularity,
    currentPeriod,
    trendWindow,
    isAtToday,
    anchor,
    customFrom,
    customTo,
    rolling,
    selectGranularity(next) {
      updateParams((p) => setGranularityAndAnchor(p, next, new Date()));
    },
    selectBucket(next, date) {
      updateParams((p) => setGranularityAndAnchor(p, next, date));
    },
    setRolling(preset) {
      updateParams((p) => {
        p.set("mode", "rolling");
        p.set("rolling", preset);
        p.delete("anchor");
        p.delete("from");
        p.delete("to");
      });
    },
    setGranularity(next) {
      updateParams((params) => setGranularityAndAnchor(params, next, anchor));
    },
    goToPrevious() {
      updateParams((params) => setGranularityAndAnchor(params, granularity, shiftAnchor(granularity, anchor, -1)));
    },
    goToNext() {
      updateParams((params) => setGranularityAndAnchor(params, granularity, shiftAnchor(granularity, anchor, 1)));
    },
    goToToday() {
      updateParams((params) => setGranularityAndAnchor(params, granularity, new Date()));
    },
    setMode(nextMode) {
      updateParams((params) => {
        params.set("mode", nextMode);
        if (nextMode === "granular") {
          params.delete("from");
          params.delete("to");
          if (!params.has("granularity")) params.set("granularity", granularity);
          if (!params.has("anchor")) params.set("anchor", anchorIso);
        }
        if (nextMode === "all") {
          params.delete("granularity");
          params.delete("anchor");
          params.delete("from");
          params.delete("to");
          params.delete("rolling");
        }
      });
    },
    setCustomRange(from, to) {
      updateParams((params) => {
        params.set("mode", "custom");
        params.set("from", from);
        params.set("to", to);
        params.delete("rolling");
      });
    },
  };
}
