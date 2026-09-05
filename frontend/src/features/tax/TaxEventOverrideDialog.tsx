import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import type { ClassifiedRealizedEvent } from "../../types/api";
import { useDeleteEventOverride, useSetEventOverride } from "./api";

/** Override di un evento realizzato specifico (FETTA 2): correggere un
 * costo di carico storico sbagliato, o escludere manualmente un evento dal
 * calcolo — mai un secondo motore, solo un'eccezione persistita accanto al
 * valore calcolato (stesso principio degli altri override fiscali). */
export function TaxEventOverrideDialog({
  event,
  onClose,
}: {
  event: ClassifiedRealizedEvent | null;
  onClose: () => void;
}) {
  const { t } = useTranslation("tax");
  const setOverride = useSetEventOverride();
  const deleteOverride = useDeleteEventOverride();
  const [amount, setAmount] = useState("");
  const [excluded, setExcluded] = useState(false);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAmount("");
    setExcluded(false);
    setNotes("");
    setError(null);
  }, [event]);

  if (!event) return null;

  const onSave = async () => {
    setError(null);
    try {
      await setOverride.mutateAsync({
        lotTransactionId: event.lot_transaction_id,
        sellTransactionId: event.sell_transaction_id,
        input: { override_gain_or_loss: amount === "" ? null : amount, excluded, notes: notes || null },
      });
      onClose();
    } catch (err) {
      setError(friendlyErrorMessage(err, t("eventOverride.saveError")));
    }
  };

  const onRemove = async () => {
    setError(null);
    try {
      await deleteOverride.mutateAsync({
        lotTransactionId: event.lot_transaction_id,
        sellTransactionId: event.sell_transaction_id,
      });
      onClose();
    } catch (err) {
      setError(friendlyErrorMessage(err, t("eventOverride.deleteError")));
    }
  };

  return (
    <Dialog open={!!event} onClose={onClose} title={t("eventOverride.title")}>
      <p className="text-sm text-text-muted">{t("eventOverride.description")}</p>
      <div className="mt-4 flex flex-col gap-3">
        <Input
          label={t("eventOverride.amountLabel")}
          placeholder={event.gain_or_loss}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm text-text">
          <input type="checkbox" checked={excluded} onChange={(e) => setExcluded(e.target.checked)} />
          {t("eventOverride.excludeLabel")}
        </label>
        <Input
          label={t("eventOverride.notesLabel")}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <div className="mt-2 flex justify-between gap-2">
          {event.is_overridden || event.excluded_reason === "user_excluded" ? (
            <Button variant="ghost" loading={deleteOverride.isPending} onClick={() => void onRemove()}>
              {t("eventOverride.remove")}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>
              {t("lossPocket.openingDialog.cancel")}
            </Button>
            <Button loading={setOverride.isPending} onClick={() => void onSave()}>
              {t("lossPocket.openingDialog.save")}
            </Button>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
