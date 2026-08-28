import { useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import { createPortal } from "react-dom";

interface FloatingPanelProps {
  open: boolean;
  anchorRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  /** "center" ancora il pannello al centro dell'anchor (menu a tendina),
   * "end" ancora il bordo destro del pannello al bordo destro dell'anchor
   * (pannello che deve restare dentro lo schermo aprendosi verso sinistra). */
  align?: "center" | "end";
  children: ReactNode;
  className?: string;
}

/** Pannello flottante in portal su `document.body`, posizionato con
 * `position: fixed` calcolato dal `getBoundingClientRect()` dell'anchor —
 * necessario perche' un `position: absolute` normale (come in `Combobox.tsx`)
 * viene tagliato/scrollato quando un antenato ha `overflow-x-auto` (bug
 * reale: lo slot del Topbar in `Topbar.tsx` ce l'ha, per contenere
 * un'eventuale pagina con controlli troppo larghi — impostare `overflow-x`
 * costringe anche `overflow-y` a diventare `auto` per la spec CSS, quindi il
 * menu del `PeriodNavigator` ci restava chiuso dentro con una scrollbar
 * invece di fluttuare sopra la pagina). Click-outside e Escape gestiti qui,
 * verificando SIA l'anchor SIA il pannello (portallato altrove nel DOM,
 * quindi non piu' un discendente DOM dell'anchor anche se lo e' nell'albero
 * React). */
export function FloatingPanel({ open, anchorRef, onClose, align = "center", children, className = "" }: FloatingPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ top: number; left?: number; right?: number } | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    function updatePosition() {
      const rect = anchorRef.current?.getBoundingClientRect();
      if (!rect) return;
      setPosition(
        align === "end"
          ? { top: rect.bottom + 4, right: window.innerWidth - rect.right }
          : { top: rect.bottom + 4, left: rect.left + rect.width / 2 },
      );
    }
    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [open, anchorRef, align]);

  useEffect(() => {
    if (!open) return undefined;
    function onMouseDown(event: MouseEvent) {
      const target = event.target as Node;
      if (anchorRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      onClose();
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, anchorRef, onClose]);

  if (!open || !position) return null;

  return createPortal(
    <div
      ref={panelRef}
      style={{
        position: "fixed",
        top: position.top,
        left: position.left,
        right: position.right,
        transform: align === "center" ? "translateX(-50%)" : undefined,
      }}
      className={`z-50 rounded-lg border border-border bg-surface shadow-lg ${className}`}
    >
      {children}
    </div>,
    document.body,
  );
}
