import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

import { hapticTap } from "./haptics";

const THRESHOLD_PX = 70;
const MAX_PULL_PX = 110;

/** Pull-to-refresh sul contenitore scorrevole `ref` (solo touch).
 * Parte solo se il contenitore e' in cima; il gesto e' passivo (non blocca lo
 * scroll). Il contenitore deve avere `overscroll-y-contain`, altrimenti Chrome
 * Android ricarica l'intera pagina con il suo pull-to-refresh nativo. */
export function usePullToRefresh(ref: RefObject<HTMLElement | null>, onRefresh: () => Promise<unknown>) {
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const refresh = useRef(onRefresh);
  useEffect(() => {
    refresh.current = onRefresh;
  });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let startY: number | null = null;
    let armed = false;
    let busy = false;

    const onStart = (e: TouchEvent) => {
      startY = el.scrollTop <= 0 && !busy && e.touches.length === 1 ? e.touches[0].clientY : null;
      armed = false;
    };
    const onMove = (e: TouchEvent) => {
      if (startY === null) return;
      if (el.scrollTop > 0) {
        startY = null;
        setPull(0);
        return;
      }
      const delta = e.touches[0].clientY - startY;
      if (delta <= 0) {
        setPull(0);
        return;
      }
      const damped = Math.min(MAX_PULL_PX, delta * 0.5);
      if (damped >= THRESHOLD_PX && !armed) {
        armed = true;
        hapticTap();
      }
      if (damped < THRESHOLD_PX) armed = false;
      setPull(damped);
    };
    const onEnd = (e?: Event) => {
      if (startY === null) return;
      startY = null;
      // Gesto interrotto dal sistema (touchcancel): si annulla, non si aggiorna.
      if (armed && !busy && e?.type !== "touchcancel") {
        busy = true;
        setRefreshing(true);
        setPull(THRESHOLD_PX);
        void refresh
          .current()
          .catch(() => undefined)
          .finally(() => {
            busy = false;
            setRefreshing(false);
            setPull(0);
          });
      } else {
        setPull(0);
      }
    };

    el.addEventListener("touchstart", onStart, { passive: true });
    el.addEventListener("touchmove", onMove, { passive: true });
    el.addEventListener("touchend", onEnd, { passive: true });
    el.addEventListener("touchcancel", onEnd, { passive: true });
    return () => {
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchmove", onMove);
      el.removeEventListener("touchend", onEnd);
      el.removeEventListener("touchcancel", onEnd);
    };
  }, [ref]);

  return { pull, refreshing, threshold: THRESHOLD_PX };
}
