import { useTranslation } from "react-i18next";

import { Dialog } from "../../components/ui/Dialog";
import type { FinancialAccount } from "../../types/api";
import { AccountForm } from "./AccountForm";

/** Solo creazione (M06+): la modifica di un conto esistente vive nella sua
 * propria pagina, `AccountEditPage` — richiesta esplicita dell'utente per
 * avere spazio per lo storico IBAN in fondo, invece di un dialog stretto.
 * Nessuno storico IBAN qui: non ne puo' esistere uno per un conto che non
 * e' stato ancora creato. */
export function AccountFormDialog({
  open,
  onClose,
  onSaved,
  initialValues,
}: {
  open: boolean;
  onClose: () => void;
  /** Es. il wizard di import, che deve sapere QUALE conto e' stato appena
   * creato per assegnarlo all'import in corso — non solo che il dialog si
   * e' chiuso. Opzionale: il chiamante che non lo passa (AccountsPage) si
   * comporta esattamente come prima. */
  onSaved?: (account: FinancialAccount) => void;
  initialValues?: { name?: string; iban?: string };
}) {
  const { t } = useTranslation("accounts");
  return (
    <Dialog open={open} onClose={onClose} title={t("form.createTitle")}>
      <AccountForm
        initialValues={initialValues}
        onSaved={(account) => {
          onSaved?.(account);
          onClose();
        }}
        onCancel={onClose}
      />
    </Dialog>
  );
}
