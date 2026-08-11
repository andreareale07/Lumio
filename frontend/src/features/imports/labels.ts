import type { ImportStatus } from "../../types/api";

export const IMPORT_STATUS_LABELS: Record<ImportStatus, string> = {
  uploaded: "Caricato",
  queued: "In coda",
  processing: "In elaborazione",
  parsing: "Estrazione in corso",
  completed: "Completato",
  failed: "Non riuscito",
  cancelled: "Annullato",
};

export const IMPORT_STATUS_TONE: Record<ImportStatus, "neutral" | "primary" | "success" | "danger"> = {
  uploaded: "neutral",
  queued: "neutral",
  processing: "primary",
  parsing: "primary",
  completed: "success",
  failed: "danger",
  cancelled: "neutral",
};
