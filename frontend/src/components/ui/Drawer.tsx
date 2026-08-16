import { useEffect } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

import { X } from "lucide-react";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Larghezza massima su desktop — default invariato per i chiamanti
   * esistenti. Un contenuto "a tutta altezza" come un viewer PDF/tabella CSV
   * (rework "elimina import") beneficia di più spazio orizzontale. */
  widthClassName?: string;
}

/** Su mobile occupa lo schermo intero (SPEC_FE §100: Drawer per dettagli
 * contestuali senza cambiare pagina), su desktop resta un pannello laterale. */
export function Drawer({ open, onClose, title, children, widthClassName = "max-w-md" }: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  // Portal su document.body, stesso motivo di Dialog.tsx: evita che un
  // dialog aperto da dentro il Drawer (es. "+ Nuova categoria") finisca
  // annidato in modo inconsistente nel DOM del genitore.
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40">
      <div
        className="absolute inset-0"
        onClick={onClose}
        role="presentation"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        className={`relative flex h-full w-full ${widthClassName} flex-col border-l border-border bg-surface p-5 shadow-lg sm:w-full`}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="drawer-title" className="text-base font-semibold text-text">
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
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
