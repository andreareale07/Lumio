import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { NAV_SECTIONS, SETTINGS_NAV_ITEM } from "../../app/navigation";

function navLinkClassName({ isActive }: { isActive: boolean }) {
  return `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    isActive ? "bg-primary/10 text-primary" : "text-text hover:bg-surface-hover"
  }`;
}

const SettingsIcon = SETTINGS_NAV_ITEM.icon;

/** Rework Navigation (SPEC_FE_REDESIGN §4-5): sidebar gerarchica a sezioni
 * invece di lista piatta di 17 voci. Le voci vivono in `app/navigation.ts`
 * (condiviso con `MobileNav`) e in `features/settings/settingsNav.ts` per
 * l'hub — "Impostazioni" è ora una singola voce, attiva su qualunque
 * `/settings/*` grazie al prefix-match di default di `NavLink`. */
export function Sidebar() {
  const { t } = useTranslation("navigation");
  return (
    <nav
      aria-label={t("ariaLabel")}
      className="hidden w-56 shrink-0 flex-col gap-4 overflow-y-auto border-r border-border bg-surface p-3 md:flex"
    >
      {NAV_SECTIONS.map((section, index) => (
        <div key={section.sectionKey ?? `section-${index}`} className="flex flex-col gap-1">
          {section.sectionKey && (
            <p className="px-3 text-xs font-semibold uppercase tracking-wide text-text-muted">
              {t(`sections.${section.sectionKey}`)}
            </p>
          )}
          {section.items.map(({ to, labelKey, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} className={navLinkClassName}>
              <Icon className="h-4 w-4" aria-hidden="true" />
              {t(`items.${labelKey}`)}
            </NavLink>
          ))}
        </div>
      ))}

      <div className="mt-auto flex flex-col gap-1 border-t border-border pt-3">
        <NavLink to={SETTINGS_NAV_ITEM.to} className={navLinkClassName}>
          <SettingsIcon className="h-4 w-4" aria-hidden="true" />
          {t(`items.${SETTINGS_NAV_ITEM.labelKey}`)}
        </NavLink>
      </div>
    </nav>
  );
}
