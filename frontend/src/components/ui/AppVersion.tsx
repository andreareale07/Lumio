import { APP_VERSION } from "../../lib/appVersion";

/** Numero di versione discreto, da mettere sotto il logo delle schermate d'ingresso. */
export function AppVersion({ className = "" }: { className?: string }) {
  return <p className={`text-xs text-text-muted ${className}`}>v{APP_VERSION}</p>;
}
