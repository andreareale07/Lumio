import { useState } from "react";
import type { ReactNode } from "react";

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

  return (
    <div className="flex h-screen flex-col">
      <Topbar toolbarSlotRef={setToolbarSlot} />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto p-4 pb-20 md:pb-4">
          <PageToolbarContext.Provider value={toolbarSlot}>{children}</PageToolbarContext.Provider>
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
