import { useRef } from "react";

/** Stima del tempo residuo per un job "x/N" in corso, basata sulla cadenza
 * REALE osservata tra un evento e l'altro — non su processed/tempo-totale,
 * che confonderebbe il "replay" iniziale dello stream SSE (tutti gli eventi
 * passati arrivano in una raffica quasi istantanea quando ci si collega a
 * un job già a metà, vedi job_events.stream()) con la velocità vera. Un
 * intervallo troppo breve tra due eventi (`_MIN_REALISTIC_GAP_MS`) viene
 * scartato dalla stima invece che interpretato come "velocissimo": è quasi
 * certamente replay, non un vero tempo di elaborazione per riga. */
export interface EtaEstimate {
  remainingSeconds: number;
  label: string;
}

const _MIN_REALISTIC_GAP_MS = 1000;
// Media mobile esponenziale: ogni nuovo campione pesa il 35% della stima,
// abbastanza reattivo da adattarsi (es. la macchina rallenta) senza
// oscillare selvaggiamente su un singolo campione anomalo.
const _EMA_ALPHA = 0.35;

interface EtaTrackerState {
  lastProcessed: number | null;
  lastTimestampMs: number | null;
  emaMsPerItem: number | null;
}

/** Hook con stato persistente tra i render (via ref, non useState: non deve
 * causare un re-render suo — è già `processed` a farlo scattare). Chiamare
 * ad ogni render con lo stato di progresso corrente; ritorna la stima
 * aggiornata o `null` finché non c'è ancora un campione realistico. */
export function useEtaEstimate(processed: number | null, total: number | null): EtaEstimate | null {
  const stateRef = useRef<EtaTrackerState>({ lastProcessed: null, lastTimestampMs: null, emaMsPerItem: null });

  if (processed == null || total == null || total <= 0 || processed >= total) {
    return null;
  }

  const now = Date.now();
  const state = stateRef.current;

  if (state.lastProcessed != null && state.lastTimestampMs != null && processed > state.lastProcessed) {
    const deltaItems = processed - state.lastProcessed;
    const deltaMs = now - state.lastTimestampMs;
    if (deltaMs >= _MIN_REALISTIC_GAP_MS) {
      const msPerItem = deltaMs / deltaItems;
      state.emaMsPerItem = state.emaMsPerItem == null ? msPerItem : _EMA_ALPHA * msPerItem + (1 - _EMA_ALPHA) * state.emaMsPerItem;
    }
    // Un salto troppo ravvicinato (replay) aggiorna comunque il puntatore
    // "ultimo visto", ma NON la stima di velocità — altrimenti il prossimo
    // intervallo realistico verrebbe misurato da un punto di partenza
    // sbagliato (conterebbe anche gli item del replay come se avessero
    // richiesto quel tempo brevissimo).
  }

  if (processed !== state.lastProcessed) {
    state.lastProcessed = processed;
    state.lastTimestampMs = now;
  }

  if (state.emaMsPerItem == null) return null;

  const remainingItems = total - processed;
  const remainingSeconds = (remainingItems * state.emaMsPerItem) / 1000;
  return { remainingSeconds, label: formatRemaining(remainingSeconds) };
}

function formatRemaining(seconds: number): string {
  if (seconds < 45) return "meno di un minuto rimanente";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `~${minutes} minut${minutes === 1 ? "o" : "i"} rimanent${minutes === 1 ? "e" : "i"}`;
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  return `~${hours}h${remMinutes > 0 ? ` ${remMinutes}m` : ""} rimanenti`;
}
