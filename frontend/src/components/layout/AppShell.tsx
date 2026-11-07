import { useRef, useState } from "react";
import type { ReactNode } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw } from "lucide-react";

import { BankConnectionsNotice } from "../../features/settings/open-banking/BankConnectionsNotice";
import { usePullToRefresh } from "../../lib/usePullToRefresh";
import { MobileNav } from "./MobileNav";
import { PageToolbarContext } from "./PageToolbarContext";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/** Contenitore del navigatore periodo/nodo DOM del Topbar (PHASE 5b),
 * tenuto qui perche' `Topbar` (che possiede il nodo) e le pagine sotto
 * `<main>` (che ci renderizzano dentro via portal) sono rami diversi
 * dell'albero — vedi `PageToolbarContext.tsx` per il perche' di un portal
 * invece di stato React passato per props/context "vivo". */
export function AppShell({ children }: { children: ReactNode }) {
  const [toolbarSlot, setToolbarSlot] = useState<HTMLDivElement | null>(null);
  const queryClient = useQueryClient();
  const mainRef = useRef<HTMLElement>(null);
  // Tira giu' in cima alla pagina: ricarica i dati delle query attive.
  const { pull, refreshing, threshold } = usePullToRefresh(mainRef, () =>
    queryClient.refetchQueries({ type: "active" }),
  );

  return (
    <div className="flex h-dvh flex-col">
      <Topbar toolbarSlotRef={setToolbarSlot} />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        {/* `overscroll-y-contain`: serve a bloccare il pull-to-refresh nativo
         * di Chrome (ricaricherebbe tutta la pagina) a favore del nostro. */}
        <main ref={mainRef} className="relative min-w-0 flex-1 overflow-y-auto overscroll-y-contain p-4 pb-20 md:pb-4">
          {pull > 0 && (
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center"
              style={{ transform: `translateY(${pull - 36}px)`, opacity: Math.min(1, pull / threshold) }}
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-surface shadow-md">
                {refreshing ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                ) : (
                  <RefreshCw
                    className="h-4 w-4 text-text-muted"
                    style={{ transform: `rotate(${(pull / threshold) * 270}deg)` }}
                  />
                )}
              </span>
            </div>
          )}
          <BankConnectionsNotice />
          <PageToolbarContext.Provider value={toolbarSlot}>{children}</PageToolbarContext.Provider>
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
