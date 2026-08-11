/** Serializza un oggetto di filtri in query string, omettendo i valori
 * assenti/vuoti. Promosso da `features/transactions/api.ts` (duplicato lì
 * prima della milestone 08) cosi' anche `features/analytics/api.ts` lo
 * riusa invece di ridefinirlo. Il parametro e' tipizzato `object` (non un
 * `Record` indicizzato) cosi' qualunque interfaccia di filtri dei chiamanti
 * resta assegnabile senza dichiarare a sua volta un index signature. */
export function buildQueryString(filters: object): string {
  const params = new URLSearchParams();
  Object.entries(filters as Record<string, string | number | undefined>).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}
