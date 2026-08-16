import { useState } from "react";
import { Check, Lock, Pencil, X } from "lucide-react";

import { Button } from "../../../components/ui/Button";
import type { JobParameter } from "../../../types/api";
import { useUpdateSystemSetting } from "./api";

/** Riga di un singolo parametro dentro la card di un job (pagina Job di
 * sistema). Editabile: soglie di stallo, salvate su `system_settings` — ha
 * effetto entro il prossimo utilizzo del job, mai un riavvio, quindi qui
 * "Salva" può davvero dirsi tale. Sola lettura: i timeout dei job (letti da
 * arq una sola volta all'avvio del worker) — mostrati con un lucchetto e il
 * motivo, mai un campo che finge di essere modificabile. */
export function JobParameterRow({ parameter }: { parameter: JobParameter }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(parameter.value ?? ""));
  const updateSetting = useUpdateSystemSetting();

  if (!parameter.editable) {
    return (
      <div className="flex items-center justify-between gap-3 py-1 text-sm">
        <span className="text-text-muted">{parameter.label}</span>
        <span
          className="flex items-center gap-1.5 text-text-muted"
          title={parameter.readonly_reason ?? undefined}
        >
          <Lock className="h-3.5 w-3.5" aria-hidden="true" />
          {String(parameter.value)} {parameter.unit}
        </span>
      </div>
    );
  }

  const handleSave = async () => {
    const parsed = Number(draft);
    if (!Number.isFinite(parsed) || parsed <= 0) return;
    await updateSetting.mutateAsync({ key: parameter.setting_key!, value: parsed });
    setEditing(false);
  };

  return (
    <div className="flex items-center justify-between gap-3 py-1 text-sm">
      <span className="text-text-muted">{parameter.label}</span>
      {editing ? (
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            min={1}
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSave();
              if (e.key === "Escape") setEditing(false);
            }}
            className="h-8 w-24 rounded-md border border-border bg-surface px-2 text-sm text-text"
          />
          <span className="text-text-muted">{parameter.unit}</span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Salva"
            loading={updateSetting.isPending}
            onClick={() => void handleSave()}
          >
            <Check className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Annulla" onClick={() => setEditing(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-1.5">
          <span className="text-text">
            {String(parameter.value)} {parameter.unit}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Modifica ${parameter.label}`}
            onClick={() => {
              setDraft(String(parameter.value ?? ""));
              setEditing(true);
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
}
