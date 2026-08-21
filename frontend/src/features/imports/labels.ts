import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import type { AiClassificationStatus, ImportStatus } from "../../types/api";

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

/** Etichetta di stato import: namespace "enums" (SPEC_FE_REDESIGN §27),
 * stesso pattern di `useTransactionTypeLabel`. */
export function useImportStatusLabel(): (status: ImportStatus) => string {
  const { t } = useTranslation("enums");
  return (status) => t(`importStatus.${status}`);
}

export function useAiClassificationStatusLabel(): (status: AiClassificationStatus) => string {
  const { t } = useTranslation("enums");
  return (status) => t(`aiClassificationStatus.${status}`);
}

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
 * insieme, non ha lo spazio verticale del wizard). Namespace "imports": non
 * e' un vero enum del backend, solo un bucket derivato dagli eventi SSE. */
export function importStageLabel(t: TFunction, stage: "queued" | "preparazione" | "estrazione" | "salvataggio"): string {
  return t(`imports:stage.${stage}`);
}

export function isActiveAiClassificationStatus(status: AiClassificationStatus | null): boolean {
  return status === "pending" || status === "running";
}
