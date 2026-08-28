/** Rendimento (Modified Dietz), puro e unit-testabile: nessuna dipendenza
 * da React/query. Standard de facto per il "rendimento personale" mostrato
 * al cliente retail (Fidelity/Vanguard/Empower) — non un TWR vero
 * (richiederebbe rivalutare il portafoglio ad ogni movimento), ma
 * un'ottima approssimazione quando i flussi non sono enormi rispetto al
 * portafoglio (il caso normale di un investitore privato). Vedi
 * `che-poi-se-stiamo-agile-nygaard.md` per la ricerca (letteratura
 * CFA/GIPS) e l'esempio numerico verificato a mano che ha guidato questa
 * implementazione.
 *
 * R = (V1 - V0 - F) / (V0 + Σ(wᵢ × Fᵢ)), wᵢ = giorni rimanenti nel periodo
 * dopo il flusso / durata totale del periodo.
 */

export interface DietzFlow {
  /** Data ISO (YYYY-MM-DD) del movimento. */
  date: string;
  /** Segno: + capitale che ENTRA nel portafoglio (buy/opening), - capitale
   * che ne ESCE (sell). Mai dividend/deposit/withdrawal/fee/tax standalone
   * (non toccano il valore delle posizioni, vedi PortfolioSummaryBlock). */
  amount: number;
}

function daysBetween(from: string, to: string): number {
  const fromMs = new Date(`${from}T00:00:00Z`).getTime();
  const toMs = new Date(`${to}T00:00:00Z`).getTime();
  return Math.round((toMs - fromMs) / 86_400_000);
}

/** Netta i flussi sullo stesso giorno (evita l'ambiguita' di ordine
 * intra-giornata, nota nella letteratura) e ordina per data crescente. */
function netFlowsByDate(flows: DietzFlow[]): DietzFlow[] {
  const byDate = new Map<string, number>();
  for (const f of flows) {
    byDate.set(f.date, (byDate.get(f.date) ?? 0) + f.amount);
  }
  return [...byDate.entries()]
    .map(([date, amount]) => ({ date, amount }))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

/** `null` se il denominatore e' zero (nessun capitale investito nel
 * periodo) — mai un errore o un'infinita', il chiamante mostra "n/d". */
export function modifiedDietzReturn(
  startValue: number,
  endValue: number,
  flows: DietzFlow[],
  periodStart: string,
  periodEnd: string,
): number | null {
  const netted = netFlowsByDate(flows);

  // Portafoglio apre durante il periodo (V0 = 0): il periodo effettivo si
  // sposta alla data del primo flusso, che diventa il nuovo inizio a peso
  // pieno (comportamento standard raccomandato) — senza flussi, non c'e'
  // capitale da valutare.
  const effectiveStart = startValue === 0 && netted.length > 0 ? netted[0]!.date : periodStart;

  const totalDays = daysBetween(effectiveStart, periodEnd);
  let weightedFlows = 0;
  let netFlowTotal = 0;
  for (const f of netted) {
    netFlowTotal += f.amount;
    // totalDays === 0: periodo degenere (apertura lo stesso giorno della
    // fine), nessun tempo per compounding -> peso pieno per costruzione.
    const weight = totalDays === 0 ? 1 : daysBetween(f.date, periodEnd) / totalDays;
    weightedFlows += weight * f.amount;
  }

  const denominator = startValue + weightedFlows;
  if (denominator === 0) return null;

  const numerator = endValue - startValue - netFlowTotal;
  return numerator / denominator;
}

export interface DietzSeriesPoint {
  /** Data ISO (YYYY-MM-DD), stessa chiave usata per ordinare/filtrare i flussi. */
  period: string;
  /** Etichetta gia' formattata per l'asse X del grafico. */
  label: string;
  /** Valore di mercato del portafoglio in questo punto (non un rendimento). */
  value: number;
}

/** Serie del rendimento CUMULATO (Modified Dietz) rispetto all'inizio del
 * periodo, un punto per ogni voce di `points` — stesso identico calcolo di
 * `modifiedDietzReturn`, applicato punto per punto (non solo a inizio/fine
 * range) cosi' il grafico "Andamento del rendimento" e il badge accanto a
 * "Valore attuale" raccontano sempre la stessa storia: l'ultimo punto di
 * questa serie coincide esattamente col rendimento del badge (stesso V0,
 * stessi flussi, stesso periodo). V0 e' fissato al valore del PRIMO punto
 * di `points` (l'inizio del range scelto nel `RangeSelector`), non
 * ricalcolato punto per punto — solo i flussi accumulati e la data di fine
 * cambiano man mano che si avanza. I punti dove `modifiedDietzReturn`
 * ritorna `null` (nessun capitale ancora investito, es. prima del primo
 * acquisto) sono omessi, non mostrati come 0% fuorviante. */
export function buildDietzReturnSeries(
  points: DietzSeriesPoint[],
  flows: DietzFlow[],
  periodStart: string,
): DietzSeriesPoint[] {
  if (points.length === 0) return [];
  const v0 = points[0]!.value;
  const series: DietzSeriesPoint[] = [];
  for (const p of points) {
    const flowsSoFar = flows.filter((f) => f.date <= p.period);
    const returnPct = modifiedDietzReturn(v0, p.value, flowsSoFar, periodStart, p.period);
    if (returnPct !== null) {
      series.push({ period: p.period, label: p.label, value: returnPct });
    }
  }
  return series;
}
