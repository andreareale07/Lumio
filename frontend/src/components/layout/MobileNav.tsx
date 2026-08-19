import { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { NavLink } from "react-router-dom";

import { NAV_SECTIONS, SETTINGS_NAV_ITEM } from "../../app/navigation";
import { Drawer } from "../ui/Drawer";

// Solo le 4 voci di uso piu' frequente stanno nella barra (SPEC_FE §9/§82:
// navigazione mobile pensata per il touch, non la sidebar rimpicciolita).
const PRIMARY_PATHS = new Set(["/", "/accounts", "/transactions", "/imports"]);
// "Transazioni" diventa "Movimenti" solo nella bottom bar (etichetta piu'
// corta gia' in uso prima di questo rework, invariata).
const PRIMARY_LABEL_OVERRIDES: Record<string, string> = { "/transactions": "Movimenti" };

function navLinkClassNamePrimary({ isActive }: { isActive: boolean }) {
  return `flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium ${
    isActive ? "text-primary" : "text-text-muted"
  }`;
}

function navLinkClassNameDrawer({ isActive }: { isActive: boolean }) {
  return `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${
    isActive ? "bg-primary/10 text-primary" : "text-text hover:bg-surface-hover"
  }`;
}

/** Rework Navigation (SPEC_FE_REDESIGN §4-5, §11): le voci ora derivano
 * dalla stessa `NAV_SECTIONS` di `Sidebar` invece di un secondo array
 * mantenuto a mano — prima le due liste erano gia' disallineate (Valuta e
 * Job di sistema mancavano da questo Drawer pur essendo in sidebar). Le 8
 * pagine Settings non compaiono piu' singolarmente: "Impostazioni" e' una
 * sola voce che porta al Settings Hub. */
export function MobileNav() {
  const [moreOpen, setMoreOpen] = useState(false);

  const allItems = NAV_SECTIONS.flatMap((section) => section.items);
  const primaryItems = allItems.filter((item) => PRIMARY_PATHS.has(item.to));
  const moreItems = [...allItems.filter((item) => !PRIMARY_PATHS.has(item.to)), SETTINGS_NAV_ITEM];

  return (
    <>
      <nav
        aria-label="Navigazione principale"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-surface md:hidden"
      >
        {primaryItems.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} className={navLinkClassNamePrimary}>
            <Icon className="h-5 w-5" aria-hidden="true" />
            {PRIMARY_LABEL_OVERRIDES[to] ?? label}
          </NavLink>
        ))}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          className="flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium text-text-muted"
        >
          <MoreHorizontal className="h-5 w-5" aria-hidden="true" />
          Altro
        </button>
      </nav>

      <Drawer open={moreOpen} onClose={() => setMoreOpen(false)} title="Altro">
        <div className="flex flex-col gap-1">
          {moreItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={() => setMoreOpen(false)} className={navLinkClassNameDrawer}>
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </div>
      </Drawer>
    </>
  );
}
