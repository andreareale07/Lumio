import { useTranslation } from "react-i18next";

import { Dialog } from "../../components/ui/Dialog";
import { AccountForm } from "./AccountForm";

/** Solo creazione (M06+): la modifica di un conto esistente vive nella sua
 * propria pagina, `AccountEditPage` — richiesta esplicita dell'utente per
 * avere spazio per lo storico IBAN in fondo, invece di un dialog stretto.
 * Nessuno storico IBAN qui: non ne puo' esistere uno per un conto che non
 * e' stato ancora creato. */
export function AccountFormDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation("accounts");
  return (
    <Dialog open={open} onClose={onClose} title={t("form.createTitle")}>
      <AccountForm onSaved={onClose} onCancel={onClose} />
    </Dialog>
  );
}
