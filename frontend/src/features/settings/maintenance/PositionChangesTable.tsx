import { useTranslation } from "react-i18next";

import { formatMoney, formatQuantity } from "../../../lib/format";
import type { PositionChange } from "../../../types/api";

function Transition({ before, after }: { before: string | null; after: string }) {
  return (
    <span className="font-numeric whitespace-nowrap">
      <span className="text-text-muted">{before ?? "—"}</span>
      <span className="px-1 text-text-muted">→</span>
      <span className="text-text">{after}</span>
    </span>
  );
}

/** Elenco di cosa e' cambiato (o cambierebbe) nel ricalcolo delle posizioni,
 * condiviso fra l'anteprima e il resoconto dell'ultima esecuzione. */
export function PositionChangesTable({ changes }: { changes: PositionChange[] }) {
  const { t } = useTranslation("settings");

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-surface-hover text-left text-xs text-text-muted">
          <tr>
            <th className="px-3 py-2 font-medium">{t("items.maintenance.positions.table.asset")}</th>
            <th className="px-3 py-2 font-medium">{t("items.maintenance.positions.table.account")}</th>
            <th className="px-3 py-2 text-right font-medium">{t("items.maintenance.positions.table.realized")}</th>
            <th className="px-3 py-2 text-right font-medium">{t("items.maintenance.positions.table.quantity")}</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((change, index) => (
            <tr key={`${change.asset}-${change.account}-${index}`} className="border-t border-border">
              <td className="px-3 py-2 text-text">{change.asset}</td>
              <td className="px-3 py-2 text-text-muted">{change.account}</td>
              <td className="px-3 py-2 text-right">
                <Transition
                  before={change.old_realized_pl === null ? null : formatMoney(change.old_realized_pl, change.currency)}
                  after={formatMoney(change.new_realized_pl, change.currency)}
                />
              </td>
              <td className="px-3 py-2 text-right">
                <Transition
                  before={change.old_quantity === null ? null : formatQuantity(change.old_quantity)}
                  after={formatQuantity(change.new_quantity)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
