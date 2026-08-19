import type { AiClassificationStatus, ImportStatus } from "../../types/api";

export const IMPORT_STATUS_LABELS: Record<ImportStatus, string> = {
  uploaded: "Caricato",
  queued: "In coda",
  processing: "In elaborazione",
  parsing: "Estrazione in corso",
  ready_for_review: "Da verificare",
  completed: "Completato",
  failed: "Non riuscito",
  cancelled: "Annullato",
};

export const IMPORT_STATUS_TONE: Record<ImportStatus, "neutral" | "primary" | "success" | "danger" | "warning"> = {
  uploaded: "neutral",
  queued: "neutral",
  processing: "primary",
  parsing: "primary",
  ready_for_review: "warning",
  completed: "success",
  failed: "danger",
  cancelled: "neutral",
};

// Rework "elimina import": il job worker scrive uno stato in cui non e' piu'
// realmente in esecuzione (completed/failed/ready_for_review) come
// ultimissimo passo prima di uscire, e "cancelled" si raggiunge solo da
// uploaded/queued (job mai partito o bloccato in coda) — quindi per questi 4
// stati non esiste MAI un job ancora attivo per quell'import, ed e' sicuro
// mostrare il conteggio reale delle transazioni collegate (potrebbero gia'
// esistere anche per "ready_for_review": le righe NEW sono gia' state
// persistite, solo le righe ambigue restano in sospeso — vedi
// Transaction Deduplication Engine, docs/SPEC_DEDUP_TRANSACTION.md).
// "uploaded"/"queued" sono eliminabili con un comportamento diverso (nessuna
// transazione ancora creata, si tenta solo di fermare il job in coda) — solo
// processing/parsing restano bloccati (vedi isActivelyProcessingImportStatus),
// perche' li' il job e' realmente in esecuzione e arq non ha un modo
// affidabile di interromperlo a meta'.
export const TERMINAL_IMPORT_STATUSES: readonly ImportStatus[] = [
  "completed",
  "failed",
  "cancelled",
  "ready_for_review",
];

export function isTerminalImportStatus(status: ImportStatus): boolean {
  return TERMINAL_IMPORT_STATUSES.includes(status);
}

export function isActivelyProcessingImportStatus(status: ImportStatus): boolean {
  return status === "processing" || status === "parsing";
}

/** Etichette di stage per l'indicatore di progresso live nella lista Import
 * (stessa terminologia a 3 stage già usata da `ImportWizard.tsx`, qui in
 * forma di stringa invece di uno step-tracker: la lista mostra molte righe
 * insieme, non ha lo spazio verticale del wizard). */
export const IMPORT_STAGE_LABELS: Record<string, string> = {
  queued: "In coda",
  preparazione: "Preparazione",
  estrazione: "Estrazione in corso",
  salvataggio: "Salvataggio",
};

/** Classificazione AI disaccoppiata dal job di import (rework UX/design):
 * 'pending'/'running' sono gli unici stati per cui vale la pena mostrare un
 * indicatore live "x/N" — gli altri sono terminali, l'import è già
 * completo. */
export const AI_CLASSIFICATION_STATUS_LABELS: Record<AiClassificationStatus, string> = {
  pending: "In coda",
  running: "Classificazione AI in corso",
  completed: "Classificazione AI completata",
  failed: "Classificazione AI non riuscita",
  skipped: "Nessuna classificazione AI necessaria",
};

export function isActiveAiClassificationStatus(status: AiClassificationStatus | null): boolean {
  return status === "pending" || status === "running";
}
