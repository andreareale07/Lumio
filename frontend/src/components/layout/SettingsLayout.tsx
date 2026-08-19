import { Outlet } from "react-router-dom";

import { BackLink } from "../ui/BackLink";

/** Layout condiviso per ogni sotto-pagina di `/settings/*` (SPEC_FE_REDESIGN
 * §7-9): aggiunge "← Impostazioni" una sola volta nell'albero delle route
 * invece che dentro ciascuna delle 8 pagine — nessuna di esse viene toccata
 * internamente in questa fase. Il Settings Hub (`/settings` esatto) non
 * passa da qui: non avrebbe senso un link "indietro" verso se stesso. */
export function SettingsLayout() {
  return (
    <div className="flex flex-col gap-3">
      <BackLink to="/settings" label="Impostazioni" />
      <Outlet />
    </div>
  );
}
