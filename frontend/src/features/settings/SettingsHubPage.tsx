import { Link } from "react-router-dom";

import { useAuth } from "../../app/providers/AuthProvider";
import { Card } from "../../components/ui/Card";
import { SETTINGS_GROUPS } from "./settingsNav";

/** Settings Hub (SPEC_FE_REDESIGN §6): indice unico per le 8 pagine di
 * configurazione, prima sciolte nella navigazione principale. Un gruppo
 * intero sparisce se tutte le sue voci sono nascoste (§9A.4) — oggi capita
 * solo per "Integrazioni" dentro "Dati e integrazioni" quando
 * `google_enabled` è false, ma "Market Data" resta comunque visibile nello
 * stesso gruppo, quindi nessun gruppo è mai vuoto nello stato attuale. */
export function SettingsHubPage() {
  const { user } = useAuth();

  const groups = SETTINGS_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.requiresGoogle || user?.google_enabled),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-text">Impostazioni</h1>
        <p className="text-sm text-text-muted">Configura il comportamento di Lumio.</p>
      </div>

      {groups.map((group) => (
        <section key={group.label} className="flex flex-col gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">{group.label}</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {group.items.map(({ to, label, description, icon: Icon }) => (
              <Link key={to} to={to}>
                <Card className="flex h-full items-start gap-3 transition-colors hover:bg-surface-hover">
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-text-muted" aria-hidden="true" />
                  <div>
                    <p className="font-medium text-text">{label}</p>
                    <p className="text-sm text-text-muted">{description}</p>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
