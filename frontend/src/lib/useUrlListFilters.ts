import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** Stato dei filtri di una lista nell'URL (fonte di verita', condivisibile):
 * la ricerca come `q`, ogni filtro a valori come parametri ripetuti
 * (`?status=active&status=inactive`). Gli altri parametri dell'URL restano
 * intatti. La ricerca usa `replace` per non riempire la cronologia a ogni tasto. */
export function useUrlListFilters(filterKeys: string[]) {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const keysSignature = filterKeys.join("|");

  const update = useCallback(
    (mutate: (params: URLSearchParams) => void, replace = false) => {
      const next = new URLSearchParams(searchParams);
      mutate(next);
      setSearchParams(next, { replace });
    },
    [searchParams, setSearchParams],
  );

  const setQuery = useCallback(
    (value: string) =>
      update((params) => {
        if (value) params.set("q", value);
        else params.delete("q");
      }, true),
    [update],
  );

  const getValues = (key: string): string[] => searchParams.getAll(key);

  const setValues = useCallback(
    (key: string, values: string[]) =>
      update((params) => {
        params.delete(key);
        for (const value of values) params.append(key, value);
      }),
    [update],
  );

  const clearAll = useCallback(
    () =>
      update((params) => {
        params.delete("q");
        for (const key of keysSignature.split("|").filter(Boolean)) params.delete(key);
      }),
    [update, keysSignature],
  );

  const hasAnyFilter = query.trim() !== "" || filterKeys.some((key) => searchParams.has(key));

  return { query, setQuery, getValues, setValues, clearAll, hasAnyFilter };
}
