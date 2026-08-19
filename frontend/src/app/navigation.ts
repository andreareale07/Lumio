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
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

export interface NavSection {
  /** Etichetta di sezione mostrata in sidebar; assente per voci standalone
   * (es. Panoramica, Import, Attività) che non appartengono a un gruppo. */
  label?: string;
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
  { items: [{ to: "/", label: "Panoramica", icon: LayoutDashboard }] },
  {
    label: "Finanze",
    items: [
      { to: "/accounts", label: "Conti", icon: Landmark },
      { to: "/transactions", label: "Transazioni", icon: ArrowLeftRight },
    ],
  },
  {
    label: "Analisi",
    items: [
      { to: "/expenses", label: "Spese", icon: Receipt },
      { to: "/income", label: "Entrate", icon: Banknote },
    ],
  },
  {
    label: "Patrimonio",
    items: [
      { to: "/net-worth", label: "Patrimonio", icon: Wallet },
      { to: "/investments", label: "Investimenti", icon: PiggyBank },
    ],
  },
  { items: [{ to: "/imports", label: "Import", icon: UploadCloud }] },
  { items: [{ to: "/activity", label: "Attività", icon: Activity }] },
];

/** Voce unica che sostituisce le 7-8 voci Settings prima sciolte nella
 * navigazione principale (SPEC_FE_REDESIGN §6). Attiva su qualunque
 * `/settings/*` grazie al prefix-match di default di `NavLink` (nessun
 * `end`, a differenza delle altre voci). */
export const SETTINGS_NAV_ITEM: NavItem = { to: "/settings", label: "Impostazioni", icon: Settings };
