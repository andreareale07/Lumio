import { LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useAuth } from "../../app/providers/AuthProvider";
import { useTheme } from "../../app/providers/ThemeProvider";
import { setLocale, SUPPORTED_LOCALES, type SupportedLocale } from "../../app/i18n";

const THEME_ICONS = { light: Sun, dark: Moon, system: Monitor } as const;

/** `toolbarSlotRef`: PHASE 5b (rework Dashboard-come-punto-d'ingresso) —
 * contenitore per le azioni di pagina (navigatore periodo, pulsante
 * "aggiungi X"), riempito via portal da `usePageToolbar` in ogni pagina
 * invece che duplicato in cima al contenuto scrollabile di ognuna. `hidden
 * md:flex`: su mobile lo spazio e' troppo stretto per un navigatore periodo
 * intero, ogni pagina mantiene il proprio controllo inline (visibile solo
 * su mobile) — stesso principio di duplicazione-per-breakpoint di
 * `Sidebar`/`MobileNav`. */
export function Topbar({ toolbarSlotRef }: { toolbarSlotRef: (el: HTMLDivElement | null) => void }) {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const { t, i18n } = useTranslation("common");
  const ThemeIcon = THEME_ICONS[theme];

  const cycleTheme = () => {
    const order = ["system", "light", "dark"] as const;
    const next = order[(order.indexOf(theme) + 1) % order.length];
    setTheme(next);
  };

  const cycleLocale = () => {
    const currentIndex = SUPPORTED_LOCALES.indexOf(i18n.language as SupportedLocale);
    const next = SUPPORTED_LOCALES[(currentIndex + 1) % SUPPORTED_LOCALES.length];
    setLocale(next);
  };

  return (
    <header className="flex h-14 items-center border-b border-border bg-surface">
      {/* Larghezza fissa `md:w-56` = stessa larghezza di `Sidebar.tsx`
       * (`w-56`): senza questo, il navigatore periodo/pulsante nel Topbar
       * comincia subito dopo "Lumio" invece che allineato con l'inizio
       * reale del contenuto della pagina sotto (h1, KPI...), che comincia
       * dopo la Sidebar — disallineamento notato dall'utente su
       * screenshot. Su mobile la Sidebar non c'e', quindi nessuna
       * larghezza fissa (l'area si restringe al testo "Lumio"). */}
      <div className="flex h-full shrink-0 items-center px-4 md:w-56">
        <span className="font-semibold text-text">Lumio</span>
      </div>
      <div className="flex min-w-0 flex-1 items-center justify-end gap-3 px-4">
        {/* `justify-end`: i controlli di pagina (periodo, "aggiungi X")
         * vanno ancorati a destra, accostati al separatore/alle icone —
         * non lasciati a sinistra subito dopo "Lumio" con uno spazio vuoto
         * in mezzo (richiesta esplicita dell'utente). Lo spazio vuoto resta
         * semplicemente prima del gruppo, non dopo. */}
        <div ref={toolbarSlotRef} className="hidden min-w-0 items-center justify-end gap-2 overflow-x-auto md:flex" />
        {/* Separatore verticale: distingue le azioni di pagina a sinistra
         * dalle impostazioni globali (lingua/tema/utente/logout) a destra —
         * sempre presente, indipendentemente dal fatto che la pagina
         * corrente abbia o meno un contenuto da mostrare nello slot. */}
        <div className="h-6 w-px shrink-0 bg-border" aria-hidden="true" />
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={cycleLocale}
            aria-label={t("language.toggle")}
            title={t(`language.${i18n.language}`)}
            className="rounded-md px-2 py-1.5 text-xs font-semibold text-text-muted hover:bg-surface-hover hover:text-text"
          >
            {i18n.language.toUpperCase()}
          </button>
          <button
            type="button"
            onClick={cycleTheme}
            aria-label={t("theme.label", { value: t(`theme.${theme}`) })}
            title={t("theme.label", { value: t(`theme.${theme}`) })}
            className="rounded-md p-2 text-text-muted hover:bg-surface-hover hover:text-text"
          >
            <ThemeIcon className="h-4 w-4" />
          </button>
          {user && <span className="hidden text-sm text-text-muted sm:inline">{user.display_name}</span>}
          <button
            type="button"
            onClick={() => void logout()}
            aria-label={t("logout")}
            title={t("logout")}
            className="rounded-md p-2 text-text-muted hover:bg-surface-hover hover:text-text"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
