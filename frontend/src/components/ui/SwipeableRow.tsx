import { useRef, useState } from "react";
import type { PointerEvent, ReactNode } from "react";

import type { LucideIcon } from "lucide-react";

import { hapticTap } from "../../lib/haptics";

export interface SwipeAction {
  label: string;
  icon: LucideIcon;
  onTrigger: () => void;
  /** Colore di sfondo mostrato sotto la riga mentre la si trascina. */
  className: string;
}

const TRIGGER_PX = 88;
const MAX_PX = 120;
// Prima di decidere se il gesto e' orizzontale (swipe) o verticale (scroll)
// si aspettano pochi pixel: cosi' lo scroll della pagina non viene mai rubato.
const LOCK_PX = 8;

/** Riga con azioni a scorrimento (solo mobile). Scorrere verso destra attiva
 * `startAction`, verso sinistra `endAction`; oltre soglia l'azione parte al
 * rilascio, con un tocco tattile quando la soglia viene superata.
 * Le azioni devono SEMPRE essere raggiungibili anche senza gesture (qui: dal
 * dettaglio del movimento), lo swipe e' solo una scorciatoia. */
export function SwipeableRow({
  children,
  startAction,
  endAction,
}: {
  children: ReactNode;
  startAction?: SwipeAction;
  endAction?: SwipeAction;
}) {
  const [dx, setDx] = useState(0);
  const [dragging, setDragging] = useState(false);
  const gesture = useRef<{ x: number; y: number; locked: "h" | "v" | null; armed: boolean } | null>(null);

  const clamp = (value: number) => {
    const min = endAction ? -MAX_PX : 0;
    const max = startAction ? MAX_PX : 0;
    return Math.max(min, Math.min(max, value));
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse") return; // desktop: nessuno swipe
    gesture.current = { x: event.clientX, y: event.clientY, locked: null, armed: false };
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const g = gesture.current;
    if (!g) return;
    const moveX = event.clientX - g.x;
    const moveY = event.clientY - g.y;
    if (!g.locked) {
      if (Math.abs(moveX) < LOCK_PX && Math.abs(moveY) < LOCK_PX) return;
      g.locked = Math.abs(moveX) > Math.abs(moveY) ? "h" : "v";
      if (g.locked === "h") {
        setDragging(true);
        event.currentTarget.setPointerCapture(event.pointerId);
      }
    }
    if (g.locked !== "h") return;
    const next = clamp(moveX);
    const armed = Math.abs(next) >= TRIGGER_PX;
    if (armed !== g.armed) {
      g.armed = armed;
      if (armed) hapticTap();
    }
    setDx(next);
  };

  const finish = () => {
    const g = gesture.current;
    gesture.current = null;
    setDragging(false);
    if (g?.locked === "h" && g.armed) {
      (dx > 0 ? startAction : endAction)?.onTrigger();
    }
    setDx(0);
  };

  const revealed = dx > 0 ? startAction : dx < 0 ? endAction : undefined;
  const Icon = revealed?.icon;

  return (
    <div className="relative overflow-hidden rounded-xl">
      {revealed && Icon && (
        <div
          aria-hidden="true"
          className={`absolute inset-0 flex items-center gap-2 px-5 text-sm font-medium text-white ${revealed.className} ${
            dx > 0 ? "justify-start" : "justify-end"
          }`}
        >
          <Icon className="h-5 w-5" />
          {revealed.label}
        </div>
      )}
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finish}
        onPointerCancel={finish}
        style={{ transform: `translateX(${dx}px)` }}
        className={`relative touch-pan-y ${dragging ? "" : "transition-transform duration-200 motion-reduce:transition-none"}`}
      >
        {children}
      </div>
    </div>
  );
}
