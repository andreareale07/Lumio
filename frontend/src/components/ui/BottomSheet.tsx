import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { X } from "lucide-react";

const CLOSE_DRAG_PX = 100;

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/** Pannello modale ancorato al bordo basso dello schermo, per i controlli
 * contestuali su smartphone (periodo, filtri): resta sempre dentro lo schermo,
 * scorre al suo interno se il contenuto e' alto e non dipende dall'hover. Ha un
 * pulsante di chiusura visibile (lo swipe da solo non basta), si chiude con
 * Escape e toccando lo sfondo. Portal su `document.body` come ogni overlay. */
export function BottomSheet({ open, onClose, title, children }: BottomSheetProps) {
  const { t } = useTranslation("common");
  const sheetRef = useRef<HTMLDivElement>(null);
  const dragStart = useRef<number | null>(null);
  const [dragY, setDragY] = useState(0);

  const endDrag = () => {
    const shouldClose = dragY > CLOSE_DRAG_PX;
    dragStart.current = null;
    setDragY(0);
    if (shouldClose) onClose();
  };

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    sheetRef.current?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end bg-black/40">
      <div className="absolute inset-0" onClick={onClose} role="presentation" />
      <div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        style={{ transform: dragY ? `translateY(${dragY}px)` : undefined }}
        className={`relative flex max-h-[92dvh] w-full flex-col rounded-t-2xl border-t border-border bg-surface px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2 shadow-lg outline-none ${
          dragStart.current === null ? "transition-transform duration-200 motion-reduce:transition-none" : ""
        }`}
      >
        {/* Maniglia: trascinarla verso il basso chiude il pannello (il pulsante
         * X resta l'alternativa senza gesture). `touch-none` toglie lo scroll
         * della pagina solo su quest'area. */}
        <div
          className="-mx-4 -mt-2 flex h-6 touch-none items-center justify-center"
          onPointerDown={(event) => {
            dragStart.current = event.clientY;
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (dragStart.current !== null) setDragY(Math.max(0, event.clientY - dragStart.current));
          }}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          <div className="h-1 w-9 rounded-full bg-border" aria-hidden="true" />
        </div>
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-text">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("actions.close")}
            className="flex h-11 w-11 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover hover:text-text"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
