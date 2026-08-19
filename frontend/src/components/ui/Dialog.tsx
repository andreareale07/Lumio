import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

import { X } from "lucide-react";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function Dialog({ open, onClose, title, children, footer }: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    panelRef.current?.querySelector<HTMLElement>("input, select, textarea, button")?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  // Portal su document.body: un Dialog puo' essere aperto da dentro un altro
  // form (es. "+ Nuova categoria" dentro il form di una regola) — renderizzato
  // in-place finirebbe come <form> annidato nel DOM, che i browser gestiscono
  // in modo inconsistente (il submit del form interno puo' degenerare in una
  // GET nativa sulla pagina invece di essere intercettato da React). Il
  // portal tiene il Dialog fuori dall'albero DOM del genitore a prescindere
  // da dove viene montato nell'albero dei componenti React.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        // Un form lungo (molti campi, es. registrazione movimento) puo'
        // superare l'altezza della viewport: senza un limite qui il pannello
        // si estende oltre lo schermo, irraggiungibile perche' solo
        // l'overlay esterno era scrollabile. `max-h-[90vh]` + `flex-col`
        // tiene titolo e footer sempre visibili, mentre SOLO il contenuto
        // centrale scorre.
        className="flex max-h-[90vh] w-full max-w-md flex-col rounded-xl border border-border bg-surface p-5 shadow-lg"
      >
        <div className="mb-4 flex shrink-0 items-center justify-between">
          <h2 id="dialog-title" className="text-base font-semibold text-text">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Chiudi"
            className="rounded-md p-1 text-text-muted hover:bg-surface-hover hover:text-text"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-y-auto">{children}</div>
        {footer && <div className="mt-5 flex shrink-0 justify-end gap-2">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
