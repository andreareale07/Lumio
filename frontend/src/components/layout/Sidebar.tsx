import {
  Activity,
  ArrowLeftRight,
  Banknote,
  Coins,
  FolderTree,
  LayoutDashboard,
  Landmark,
  LineChart,
  Link2,
  ListChecks,
  PiggyBank,
  Receipt,
  Sparkles,
  Tags,
  UploadCloud,
  Wallet,
  Wand2,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../../app/providers/AuthProvider";

const NAV_ITEMS = [
  { to: "/", label: "Panoramica", icon: LayoutDashboard },
  { to: "/accounts", label: "Conti", icon: Landmark },
  { to: "/transactions", label: "Transazioni", icon: ArrowLeftRight },
  { to: "/expenses", label: "Spese", icon: Receipt },
  { to: "/income", label: "Entrate", icon: Banknote },
  { to: "/net-worth", label: "Patrimonio", icon: Wallet },
  { to: "/investments", label: "Investimenti", icon: PiggyBank },
  { to: "/imports", label: "Import", icon: UploadCloud },
  { to: "/activity", label: "Attività", icon: Activity },
  { to: "/settings/categories", label: "Categorie", icon: FolderTree },
  { to: "/settings/rules", label: "Regole", icon: Wand2 },
  { to: "/settings/ai", label: "AI", icon: Sparkles },
  { to: "/settings/market-data", label: "Market Data", icon: LineChart },
  { to: "/settings/currency", label: "Valuta", icon: Coins },
  { to: "/settings/transaction-types", label: "Tipi di transazione", icon: Tags },
  { to: "/settings/jobs", label: "Job di sistema", icon: ListChecks },
];

/** Milestone 08: aggiunte Panoramica/Spese/Entrate/Patrimonio (SPEC §41).
 * Milestone 09: aggiunte Investimenti e Market Data.
 * Milestone 09.5: aggiunta Tipi di transazione (mappatura configurabile).
 * Milestone 06.5 (audit retroattivo): aggiunta Categorie (gestione completa,
 * prima limitata alla creazione al volo dentro CategoryPicker).
 * Milestone 10: "Integrazioni" mostrata SOLO se `google_enabled` (isolamento
 * reale, non un placeholder disabilitato — con GOOGLE_ENABLED=false questa
 * voce non esiste affatto, ne' nel menu ne' come route).
 * Rework "Job di sistema": pagina di configurazione dei job schedulati
 * (soglie di stallo, on/off) — raggiungibile da qualunque utente autenticato
 * per ora, nessun ruolo admin di istanza esiste ancora. */
export function Sidebar() {
  const { user } = useAuth();
  const items = user?.google_enabled
    ? [...NAV_ITEMS, { to: "/settings/integrations", label: "Integrazioni", icon: Link2 }]
    : NAV_ITEMS;

  return (
    <nav
      aria-label="Navigazione principale"
      className="hidden w-56 shrink-0 flex-col gap-1 border-r border-border bg-surface p-3 md:flex"
    >
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          className={({ isActive }) =>
            `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive ? "bg-primary/10 text-primary" : "text-text hover:bg-surface-hover"
            }`
          }
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
