import { ArrowLeftRight, Landmark, UploadCloud, Wand2 } from "lucide-react";
import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/accounts", label: "Conti", icon: Landmark },
  { to: "/transactions", label: "Movimenti", icon: ArrowLeftRight },
  { to: "/imports", label: "Import", icon: UploadCloud },
  { to: "/settings/rules", label: "Regole", icon: Wand2 },
];

/** SPEC_FE §9: su mobile una navigazione dedicata pensata per il touch, non
 * la sidebar compressa. */
export function MobileNav() {
  return (
    <nav
      aria-label="Navigazione principale"
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-surface md:hidden"
    >
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
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
    </nav>
  );
}
