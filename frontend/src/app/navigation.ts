import {
  Activity,
  ArrowLeftRight,
  Banknote,
  LayoutDashboard,
  Landmark,
  PiggyBank,
  Receipt,
  Settings,
  UploadCloud,
  Wallet,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";

export interface NavItem {
  to: string;
  /** Chiave nel namespace i18next "navigation" (`items.<labelKey>`) — mai
   * un'etichetta letterale (SPEC_FE_REDESIGN PHASE 3, rework i18n). */
  labelKey: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

export interface NavSection {
  /** Chiave `sections.<sectionKey>` nel namespace "navigation"; assente per
   * voci standalone (es. Panoramica, Import, Attività) che non appartengono
   * a un gruppo. */
  sectionKey?: string;
  items: NavItem[];
}

/** Sorgente unica della navigazione principale (SPEC_FE_REDESIGN §4-5:
 * gerarchica e dichiarativa, non piu' una lista piatta). Consumata sia da
 * `Sidebar` (desktop) sia da `MobileNav` — prima erano due array mantenuti a
 * mano che si erano gia' disallineati (Valuta/Job di sistema mancavano dal
 * menu mobile). Le pagine di Impostazioni non compaiono qui: vivono in
 * `features/settings/settingsNav.ts` e sono raggiungibili tramite la
 * singola voce `SETTINGS_NAV_ITEM` sotto, che porta al Settings Hub. */
export const NAV_SECTIONS: NavSection[] = [
  { items: [{ to: "/", labelKey: "dashboard", icon: LayoutDashboard }] },
  {
    sectionKey: "finance",
    items: [
      { to: "/accounts", labelKey: "accounts", icon: Landmark },
      { to: "/transactions", labelKey: "transactions", icon: ArrowLeftRight },
    ],
  },
  {
    sectionKey: "analytics",
    items: [
      { to: "/expenses", labelKey: "expenses", icon: Receipt },
      { to: "/income", labelKey: "income", icon: Banknote },
    ],
  },
  {
    sectionKey: "wealth",
    items: [
      { to: "/net-worth", labelKey: "netWorth", icon: Wallet },
      { to: "/investments", labelKey: "investments", icon: PiggyBank },
    ],
  },
  { items: [{ to: "/imports", labelKey: "imports", icon: UploadCloud }] },
  { items: [{ to: "/activity", labelKey: "activity", icon: Activity }] },
];

/** Voce unica che sostituisce le 7-8 voci Settings prima sciolte nella
 * navigazione principale (SPEC_FE_REDESIGN §6). Attiva su qualunque
 * `/settings/*` grazie al prefix-match di default di `NavLink` (nessun
 * `end`, a differenza delle altre voci). */
export const SETTINGS_NAV_ITEM: NavItem = { to: "/settings", labelKey: "settings", icon: Settings };
