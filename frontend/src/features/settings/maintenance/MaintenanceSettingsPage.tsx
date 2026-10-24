import { useTranslation } from "react-i18next";

import { PositionsRecomputePanel } from "./PositionsRecomputePanel";

/** Pagina Impostazioni > Manutenzione — operazioni di riparazione/ricalcolo
 * lanciabili a mano, ciascuna con anteprima e un resoconto di cosa e'
 * cambiato. Oggi raggiungibile da qualunque utente autenticato: nessun ruolo
 * esiste ancora (vedi JobsSettingsPage). */
export function MaintenanceSettingsPage() {
  const { t } = useTranslation("settings");

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-text">{t("items.maintenance.label")}</h1>
        <p className="text-sm text-text-muted">{t("items.maintenance.description")}</p>
      </div>
      <PositionsRecomputePanel />
    </div>
  );
}
