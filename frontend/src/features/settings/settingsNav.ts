import { Activity, Coins, FolderTree, Link2, ListChecks, Percent, Sparkles, LineChart, Tags, Wand2, Wrench } from "lucide-react";
import type { ComponentType, SVGProps } from "react";

export interface SettingsPageLink {
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Chiave `items.<itemKey>.label`/`items.<itemKey>.description` nel
   * namespace i18next "settings" (SPEC_FE_REDESIGN PHASE 3). */
  itemKey: string;
  /** Se true, la voce compare solo quando `user.google_enabled` è vero —
   * stesso gating già applicato oggi a livello di route (`RequireGoogleEnabled`
   * in AppRouter), qui replicato solo per la visibilità nell'hub. */
  requiresGoogle?: boolean;
}

export interface SettingsGroup {
  /** Chiave `groups.<groupKey>` nel namespace "settings". */
  groupKey: string;
  items: SettingsPageLink[];
}

/** Classificazione delle 8 pagine Settings esistenti (SPEC_FE_REDESIGN §6),
 * verificata contro il repository — nessuna pagina orfana, nessun gruppo
 * inventato. Campo `requiredRole` da aggiungere qui in futuro per il filtro
 * per ruolo (§9A.3/§9A.4): oggi nessuna pagina lo popola, RBAC non esiste
 * ancora (§9A.8). */
export const SETTINGS_GROUPS: SettingsGroup[] = [
  {
    groupKey: "finance",
    items: [
      { to: "/settings/categories", icon: FolderTree, itemKey: "categories" },
      { to: "/settings/transaction-types", icon: Tags, itemKey: "transactionTypes" },
      { to: "/settings/currency", icon: Coins, itemKey: "currency" },
      { to: "/settings/tax", icon: Percent, itemKey: "tax" },
    ],
  },
  {
    groupKey: "automation",
    items: [
      { to: "/settings/rules", icon: Wand2, itemKey: "rules" },
      { to: "/settings/ai", icon: Sparkles, itemKey: "ai" },
      { to: "/settings/ai-engine", icon: Activity, itemKey: "aiEngine" },
    ],
  },
  {
    groupKey: "dataIntegrations",
    items: [
      { to: "/settings/market-data", icon: LineChart, itemKey: "marketData" },
      { to: "/settings/integrations", icon: Link2, itemKey: "integrations", requiresGoogle: true },
    ],
  },
  {
    groupKey: "system",
    items: [
      { to: "/settings/jobs", icon: ListChecks, itemKey: "jobs" },
      { to: "/settings/maintenance", icon: Wrench, itemKey: "maintenance" },
    ],
  },
];
