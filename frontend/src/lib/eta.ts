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
 * aggiornata o `null` finché non c'è ancora nessun dato utile.
 *
 * `startedAtIso`, se noto, da' una stima "media da inizio" (processate
 * finora / tempo trascorso dall'avvio REALE del job) disponibile SUBITO,
 * anche prima che arrivi un solo evento live realistico — utile perche'
 * l'EMA da sola resta `null` finche' non osserva un intervallo vero tra due
 * eventi, il che su un job lento (secondi per riga) puo' voler dire restare
 * senza stima per un bel po' dopo aver aperto la pagina. Usata SOLO come
 * fallback finche' l'EMA non ha ancora un valore: una volta che arrivano
 * eventi live reali, l'EMA la sostituisce perche' piu' reattiva a un
 * rallentamento/accelerazione in corso (la media-da-inizio si aggiorna
 * lentissimamente su un job che ha gia' accumulato molte ore). */
export function useEtaEstimate(
  processed: number | null,
  total: number | null,
  startedAtIso?: string | null,
): EtaEstimate | null {
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

  const remainingItems = total - processed;

  if (state.emaMsPerItem != null) {
    const remainingSeconds = (remainingItems * state.emaMsPerItem) / 1000;
    return { remainingSeconds, label: formatRemaining(remainingSeconds) };
  }

  if (startedAtIso && processed > 0) {
    const elapsedMs = now - new Date(startedAtIso).getTime();
    if (elapsedMs > 0) {
      const avgMsPerItem = elapsedMs / processed;
      const remainingSeconds = (remainingItems * avgMsPerItem) / 1000;
      return { remainingSeconds, label: formatRemaining(remainingSeconds) };
    }
  }

  return null;
}

function formatRemaining(seconds: number): string {
  if (seconds < 45) return "meno di un minuto rimanente";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `~${minutes} minut${minutes === 1 ? "o" : "i"} rimanent${minutes === 1 ? "e" : "i"}`;
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  return `~${hours}h${remMinutes > 0 ? ` ${remMinutes}m` : ""} rimanenti`;
}
