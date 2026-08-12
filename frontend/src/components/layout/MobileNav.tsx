import { useState } from "react";
import {
  ArrowLeftRight,
  Banknote,
  FolderTree,
  LayoutDashboard,
  Landmark,
  LineChart,
  Link2,
  MoreHorizontal,
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
import { Drawer } from "../ui/Drawer";

// Solo le 4 voci di uso piu' frequente stanno nella barra (SPEC_FE §9/§82:
// navigazione mobile pensata per il touch, non la sidebar rimpicciolita —
// 9 voci in una bottom bar sarebbero illeggibili). Le altre, incluse le
// nuove pagine analytics della milestone 08, vivono nel Drawer "Altro".
const PRIMARY_ITEMS = [
  { to: "/", label: "Panoramica", icon: LayoutDashboard },
  { to: "/accounts", label: "Conti", icon: Landmark },
  { to: "/transactions", label: "Movimenti", icon: ArrowLeftRight },
  { to: "/imports", label: "Import", icon: UploadCloud },
];

const MORE_ITEMS = [
  { to: "/expenses", label: "Spese", icon: Receipt },
  { to: "/income", label: "Entrate", icon: Banknote },
  { to: "/net-worth", label: "Patrimonio", icon: Wallet },
  { to: "/investments", label: "Investimenti", icon: PiggyBank },
  { to: "/settings/categories", label: "Categorie", icon: FolderTree },
  { to: "/settings/rules", label: "Regole", icon: Wand2 },
  { to: "/settings/ai", label: "AI", icon: Sparkles },
  { to: "/settings/market-data", label: "Market Data", icon: LineChart },
  { to: "/settings/transaction-types", label: "Tipi di transazione", icon: Tags },
];

export function MobileNav() {
  const [moreOpen, setMoreOpen] = useState(false);
  const { user } = useAuth();
  const moreItems = user?.google_enabled
    ? [...MORE_ITEMS, { to: "/settings/integrations", label: "Integrazioni", icon: Link2 }]
    : MORE_ITEMS;

  return (
    <>
      <nav
        aria-label="Navigazione principale"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-surface md:hidden"
      >
        {PRIMARY_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium ${
                isActive ? "text-primary" : "text-text-muted"
              }`
            }
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
            {label}
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
            <NavLink
              key={to}
              to={to}
              onClick={() => setMoreOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${
                  isActive ? "bg-primary/10 text-primary" : "text-text hover:bg-surface-hover"
                }`
              }
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </div>
      </Drawer>
    </>
  );
}
