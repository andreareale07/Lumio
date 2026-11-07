import { AlertTriangle } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../../../app/providers/AuthProvider";
import { useBankConnections } from "./api";
import { needsRenewal, statusKeyOf } from "./bankStatus";

/** Avviso globale sottile quando un consenso bancario sta per scadere o e'
 * scaduto: senza rinnovo la sincronizzazione si ferma in silenzio, quindi
 * l'utente va avvisato fuori dalla pagina delle impostazioni. Non fa nessuna
 * richiesta con `OPEN_BANKING_ENABLED=false`. */
export function BankConnectionsNotice() {
  const { user } = useAuth();
  const enabled = user?.open_banking_enabled === true;
  const { t } = useTranslation("settings");
  const { data } = useBankConnections({ enabled });
  const { pathname } = useLocation();
  // Nella pagina di gestione lo stato e' gia' in evidenza sulla riga della banca.
  if (!enabled || !data || pathname === "/settings/bank-connections") return null;

  const attention = data.filter(needsRenewal);
  if (attention.length === 0) return null;
  const expired = attention.some((connection) => statusKeyOf(connection) === "expired");

  return (
    <div
      role="status"
      className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-warning/40 bg-warning-bg px-3 py-2 text-sm text-warning"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        {t(expired ? "items.bankConnections.notice.expired" : "items.bankConnections.notice.expiring", {
          count: attention.length,
          banks: attention.map((connection) => connection.aspsp_name).join(", "),
        })}
      </span>
      <Link
        to="/settings/bank-connections"
        className="inline-flex min-h-11 items-center font-medium underline md:min-h-0"
      >
        {t("items.bankConnections.notice.action")}
      </Link>
    </div>
  );
}
