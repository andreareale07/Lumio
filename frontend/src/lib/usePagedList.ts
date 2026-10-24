import { useEffect, useMemo, useState } from "react";

export interface PagedList<T> {
  page: number;
  pageCount: number;
  pageItems: T[];
  /** 1-based, inclusivi: "da 16 a 30 di 142". Entrambi 0 se la lista e' vuota. */
  from: number;
  to: number;
  total: number;
  setPage: (page: number) => void;
}

/** Paginazione lato client per elenchi che l'API restituisce interi (regole,
 * mapping, profili...). Si riporta da sola alla pagina 1 quando cambia la
 * lista di partenza in modo sostanziale (ricerca, filtro) e non lascia mai
 * una pagina oltre l'ultima dopo un'eliminazione. */
export function usePagedList<T>(items: T[], pageSize: number, resetKey: string): PagedList<T> {
  const [page, setPageState] = useState(1);
  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    setPageState(1);
  }, [resetKey]);

  const current = Math.min(page, pageCount);

  const pageItems = useMemo(
    () => items.slice((current - 1) * pageSize, current * pageSize),
    [items, current, pageSize],
  );

  return {
    page: current,
    pageCount,
    pageItems,
    from: total === 0 ? 0 : (current - 1) * pageSize + 1,
    to: Math.min(current * pageSize, total),
    total,
    setPage: (next) => setPageState(Math.min(Math.max(1, next), pageCount)),
  };
}
