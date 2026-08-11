import { Sparkles } from "lucide-react";

import { Badge } from "../../components/ui/Badge";
import type { Classification } from "../../types/api";

/** SPEC_FE §26: comunica la provenienza della classificazione, mai una
 * verità assoluta. `user` (correzione) e `manual` (scelta alla creazione)
 * sono entrambe classificazioni dirette dell'utente — indistinguibili per
 * questo indicatore, la distinzione serve solo al motore suggerimenti
 * (backend). `system` non è ancora scritto da nessun percorso in M06,
 * incluso per completezza dello schema. */
export function ClassificationIndicator({ classification }: { classification: Classification | null | undefined }) {
  if (!classification) {
    return <Badge tone="neutral">Non categorizzato</Badge>;
  }

  switch (classification.method) {
    case "rule":
      return <Badge tone="primary">● Regola</Badge>;
    case "manual":
    case "user":
      return <Badge tone="neutral">● Manuale</Badge>;
    case "system":
      return <Badge tone="neutral">● Sistema</Badge>;
    case "ai": {
      const score = classification.score ? Math.round(Number(classification.score) * 100) : null;
      return (
        <Badge tone="warning">
          <Sparkles className="h-3 w-3" /> AI{score !== null ? ` ${score}%` : ""}
        </Badge>
      );
    }
    default:
      return <Badge tone="neutral">Non categorizzato</Badge>;
  }
}
