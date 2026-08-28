/** Statistica di base condivisa (media/mediana), puro e unit-testabile:
 * nessuna dipendenza da React/query. `median()` era prima duplicata solo
 * in `DashboardPage.tsx` ("mesi di autonomia"/"vs mese tipico") — qui
 * anche `mean()` (media aritmetica, richiesta esplicitamente dall'utente
 * per "quanto spendo di media" — non la stessa cosa della mediana usata
 * per "mese tipico"). Array vuoto -> `0` per entrambe (nessun `NaN` da
 * propagare ai chiamanti: un valore assente e' meglio rappresentato a
 * monte, es. `undefined`, non da un `0/0`). */

export function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1]! + sorted[mid]!) / 2 : sorted[mid]!;
}

/** Media/mediana mobile su una finestra di `window` valori consecutivi
 * (redesign Spese/Entrate, FETTA 1) — usata per la linea "tipico" del
 * grafico Andamento. Finestra troppo grande (`window > values.length`)
 * degrada a `mean`/`median` sull'intero array invece di ritornare un
 * array vuoto: meglio un'unica linea piatta che nessuna linea. */
export function movingAverage(values: number[], window: number): number[] {
  if (values.length === 0) return [];
  const w = Math.min(Math.max(1, window), values.length);
  return values.map((_, i) => {
    const start = Math.max(0, i - w + 1);
    return mean(values.slice(start, i + 1));
  });
}

export function movingMedian(values: number[], window: number): number[] {
  if (values.length === 0) return [];
  const w = Math.min(Math.max(1, window), values.length);
  return values.map((_, i) => {
    const start = Math.max(0, i - w + 1);
    return median(values.slice(start, i + 1));
  });
}

/** Uno scostamento merita un segnale (freccia colorata, badge) solo se
 * supera SIA una soglia relativa SIA una soglia assoluta — estratta da
 * `DashboardPage.tsx` (PHASE 5) perche' ora la usano anche le pagine
 * Spese/Entrate (redesign, FETTA 1): un flag colorato per un rumore di
 * poche decine di euro e' peggio che inutile. `baseline === 0` e' un caso
 * limite reale (mese fantasma escluso a monte, ma la mediana di un solo
 * punto puo' comunque essere 0) — qualunque valore diverso da zero e'
 * allora sempre significativo. */
export function isSignificantChange(current: number, baseline: number): boolean {
  if (baseline === 0) return current !== 0;
  const relative = Math.abs((current - baseline) / baseline);
  const absolute = Math.abs(current - baseline);
  return relative >= 0.1 && absolute >= 50;
}
