import { useEffect, useState } from "react";
import { MoreHorizontal, X } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { NAV_SECTIONS, SETTINGS_NAV_ITEM } from "../../app/navigation";

// Solo le 4 voci di uso piu' frequente stanno nella barra (SPEC_FE §9/§82:
// navigazione mobile pensata per il touch, non la sidebar rimpicciolita).
const PRIMARY_PATHS = new Set(["/", "/accounts", "/transactions", "/imports"]);
// "Transazioni" diventa "Movimenti" solo nella bottom bar (etichetta piu'
// corta gia' in uso prima di questo rework, invariata).
const PRIMARY_LABEL_KEY_OVERRIDES: Record<string, string> = { "/transactions": "movements" };

// Tutte le celle (barra + voci espanse) condividono la stessa griglia: con
// colonne `1fr` (non `minmax(0,1fr)`) la larghezza di ogni colonna e' quella
// dell'etichetta piu' lunga, quindi nessun testo viene mai troncato. Anche le
// celle chiuse (altezza 0) contano nella larghezza, cosi' la barra non cambia
// aspetto aprendosi.
const CELL_BASE =
  "flex flex-col items-center justify-center gap-[3px] overflow-hidden whitespace-nowrap rounded-xl px-1 text-[11px] font-medium leading-[1.15] transition-[max-height,min-height,padding,margin,opacity] duration-300 ease-out";
const CELL_VISIBLE = "m-0.5 min-h-[58px] max-h-20 py-1.5 opacity-100";
const CELL_COLLAPSED = "m-0 min-h-0 max-h-0 py-0 opacity-0";

function cellClassName(isActive: boolean, visible: boolean) {
  const color = isActive ? "bg-primary/10 text-primary" : "text-text-muted hover:bg-surface-hover";
  return `${CELL_BASE} ${visible ? CELL_VISIBLE : CELL_COLLAPSED} ${color}`;
}

/** Rework Navigation (SPEC_FE_REDESIGN §4-5, §11): le voci derivano dalla
 * stessa `NAV_SECTIONS` di `Sidebar` invece di un secondo array mantenuto a
 * mano. Le 8 pagine Settings non compaiono singolarmente: "Impostazioni" e'
 * una sola voce che porta al Settings Hub.
 *
 * "Altro" non apre piu' un Drawer: la barra sale verso l'alto e mostra le
 * altre voci, stesso formato icona+etichetta, a partire dal primo slot a
 * sinistra sotto la riga principale; "Altro" diventa "Chiudi". */
export function MobileNav() {
  const [moreOpen, setMoreOpen] = useState(false);
  const { t } = useTranslation("navigation");
  const { pathname } = useLocation();

  const allItems = NAV_SECTIONS.flatMap((section) => section.items);
  const primaryItems = allItems.filter((item) => PRIMARY_PATHS.has(item.to));
  const moreItems = [...allItems.filter((item) => !PRIMARY_PATHS.has(item.to)), SETTINGS_NAV_ITEM];
  // Una voce nascosta e' la pagina corrente: "Altro" lo segnala da chiuso.
  const moreActive = moreItems.some((item) => pathname === item.to || pathname.startsWith(`${item.to}/`));

  useEffect(() => {
    if (!moreOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMoreOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [moreOpen]);

  const ToggleIcon = moreOpen ? X : MoreHorizontal;

  return (
    <>
      <div
        aria-hidden="true"
        onClick={() => setMoreOpen(false)}
        className={`fixed inset-0 z-30 bg-black/35 transition-opacity duration-300 md:hidden ${
          moreOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <nav
        aria-label={t("ariaLabel")}
        className="fixed inset-x-0 bottom-0 z-40 rounded-t-2xl border-t border-border bg-surface px-1 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-1.5 md:hidden"
      >
        <div className="grid grid-cols-[repeat(5,1fr)]">
          {primaryItems.map(({ to, labelKey, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setMoreOpen(false)}
              className={({ isActive }) => cellClassName(isActive, true)}
            >
              <Icon className="h-[22px] w-[22px]" aria-hidden="true" />
              <span>{t(`items.${PRIMARY_LABEL_KEY_OVERRIDES[to] ?? labelKey}`)}</span>
            </NavLink>
          ))}
          <button
            type="button"
            aria-expanded={moreOpen}
            onClick={() => setMoreOpen((open) => !open)}
            className={cellClassName(moreActive && !moreOpen, true)}
          >
            <ToggleIcon className="h-[22px] w-[22px]" aria-hidden="true" />
            <span>{moreOpen ? t("items.close") : t("items.more")}</span>
          </button>
          {moreItems.map(({ to, labelKey, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              tabIndex={moreOpen ? 0 : -1}
              aria-hidden={moreOpen ? undefined : true}
              onClick={() => setMoreOpen(false)}
              className={({ isActive }) => cellClassName(isActive, moreOpen)}
            >
              <Icon className="h-[22px] w-[22px]" aria-hidden="true" />
              <span>{t(`items.${labelKey}`)}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </>
  );
}
