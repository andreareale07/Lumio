import { AlertTriangle } from "lucide-react";

import { Button } from "./Button";

/** SPEC_FE §56: mai un messaggio tecnico grezzo, sempre un'azione di
 * recupero quando ha senso. */
export function ErrorState({
  message = "Non siamo riusciti a caricare i dati.",
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-border bg-surface p-10 text-center">
      <AlertTriangle className="h-8 w-8 text-danger" />
      <p className="text-text">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-2">
          Riprova
        </Button>
      )}
    </div>
  );
}
