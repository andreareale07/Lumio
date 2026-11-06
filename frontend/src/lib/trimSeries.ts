/** Taglia i punti iniziali "vuoti" di una serie temporale: un tratto a zero
 * prima del primo dato reale non e' un valore, e' assenza di dati, e
 * schiaccia l'andamento (curva ripida dopo anni piatti). Tiene sempre almeno
 * `minPoints` punti finali per non produrre grafici degeneri. Funzione pura,
 * non muta l'array. */
export function trimLeadingEmpty<T>(points: readonly T[], isEmpty: (point: T) => boolean, minPoints = 3): T[] {
  const firstWithData = points.findIndex((p) => !isEmpty(p));
  // Nessun dato in tutta la serie: nulla da tagliare, ci pensa l'empty state.
  if (firstWithData <= 0) return [...points];
  const start = Math.min(firstWithData, Math.max(0, points.length - minPoints));
  return points.slice(start);
}
