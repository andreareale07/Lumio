import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** Intervallo (preset 1G…Max) di un grafico di prezzo/portfolio, nell'URL
 * (`?range=3M`) cosi' e' condivisibile; senza parametro si riparte
 * dall'ultimo scelto nella famiglia di pagine (sessionStorage) e, in
 * mancanza, dal default della pagina. Non confligge con `usePeriodNavigator`
 * (altre chiavi: `mode`/`granularity`/...). */
export function useRangeParam<P extends string>(
  family: string,
  presets: readonly P[],
  fallback: P,
): [P, (next: P) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const storageKey = `lumio.range.${family}`;

  const fromUrl = searchParams.get("range");
  let stored: string | null = null;
  try {
    stored = sessionStorage.getItem(storageKey);
  } catch {
    stored = null;
  }
  const isValid = (value: string | null): value is P => value !== null && (presets as readonly string[]).includes(value);
  const value: P = isValid(fromUrl) ? fromUrl : isValid(stored) ? stored : fallback;

  const setValue = useCallback(
    (next: P) => {
      try {
        sessionStorage.setItem(storageKey, next);
      } catch {
        /* storage non disponibile: si perde solo la memoria */
      }
      const params = new URLSearchParams(searchParams);
      params.set("range", next);
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams, storageKey],
  );

  return [value, setValue];
}
