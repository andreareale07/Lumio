import { ArrowLeftRight, Landmark, UploadCloud, Wand2 } from "lucide-react";
import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/accounts", label: "Conti", icon: Landmark },
  { to: "/transactions", label: "Transazioni", icon: ArrowLeftRight },
  { to: "/imports", label: "Import", icon: UploadCloud },
  { to: "/settings/rules", label: "Regole", icon: Wand2 },
];

/** Solo le voci che esistono davvero in questa slice (SPEC_FE §11 non
 * impone di anticipare Overview/Expenses/Income/Net Worth/Investments,
 * non ancora costruiti — vedi piano). */
export function Sidebar() {
  return (
    <nav
      aria-label="Navigazione principale"
      className="hidden w-56 shrink-0 flex-col gap-1 border-r border-border bg-surface p-3 md:flex"
    >
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
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
