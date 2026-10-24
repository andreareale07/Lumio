/** Rapporto (unita' nuove per 1 vecchia) -> coppia "N vecchie : M nuove" che
 * l'utente legge sul comunicato della societa' (0.0001 -> 10000:1). */
export function ratioToUnits(ratio: string): { oldUnits: string; newUnits: string } {
  const value = Number(ratio);
  if (!Number.isFinite(value) || value <= 0) return { oldUnits: "1", newUnits: "1" };
  if (value < 1) return { oldUnits: String(Math.round(1 / value)), newUnits: "1" };
  return { oldUnits: "1", newUnits: String(Math.round(value)) };
}
