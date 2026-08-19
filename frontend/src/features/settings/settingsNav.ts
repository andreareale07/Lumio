import { Coins, FolderTree, Link2, ListChecks, Sparkles, LineChart, Tags, Wand2 } from "lucide-react";

import type { NavItem } from "../../app/navigation";

export interface SettingsPageLink extends NavItem {
  description: string;
  /** Se true, la voce compare solo quando `user.google_enabled` è vero —
   * stesso gating già applicato oggi a livello di route (`RequireGoogleEnabled`
   * in AppRouter), qui replicato solo per la visibilità nell'hub. */
  requiresGoogle?: boolean;
}

export interface SettingsGroup {
  label: string;
  items: SettingsPageLink[];
}

/** Classificazione delle 8 pagine Settings esistenti (SPEC_FE_REDESIGN §6),
 * verificata contro il repository — nessuna pagina orfana, nessun gruppo
 * inventato. Campo `requiredRole` da aggiungere qui in futuro per il filtro
 * per ruolo (§9A.3/§9A.4): oggi nessuna pagina lo popola, RBAC non esiste
 * ancora (§9A.8). */
export const SETTINGS_GROUPS: SettingsGroup[] = [
  {
    label: "Finanze",
    items: [
      {
        to: "/settings/categories",
        label: "Categorie",
        icon: FolderTree,
        description: "Gestisci le categorie usate per classificare le transazioni.",
      },
      {
        to: "/settings/transaction-types",
        label: "Tipi di transazione",
        icon: Tags,
        description: "Mappa le etichette grezze del tuo estratto conto sui tipi di transazione di Lumio.",
      },
      {
        to: "/settings/currency",
        label: "Valuta",
        icon: Coins,
        description: "Imposta la valuta di riferimento del workspace.",
      },
    ],
  },
  {
    label: "Automazione",
    items: [
      {
        to: "/settings/rules",
        label: "Regole",
        icon: Wand2,
        description: "Classifica automaticamente le transazioni in base a criteri che definisci.",
      },
      {
        to: "/settings/ai",
        label: "AI",
        icon: Sparkles,
        description: "Configura un provider AI opzionale per la classificazione automatica.",
      },
    ],
  },
  {
    label: "Dati e integrazioni",
    items: [
      {
        to: "/settings/market-data",
        label: "Market Data",
        icon: LineChart,
        description: "Configura il provider di quotazioni per l'aggiornamento prezzi degli investimenti.",
      },
      {
        to: "/settings/integrations",
        label: "Integrazioni",
        icon: Link2,
        description: "Esporta i tuoi dati finanziari su Google Sheets.",
        requiresGoogle: true,
      },
    ],
  },
  {
    label: "Sistema",
    items: [
      {
        to: "/settings/jobs",
        label: "Job di sistema",
        icon: ListChecks,
        description: "Configura i job automatici e quelli innescati dalle tue azioni.",
      },
    ],
  },
];
