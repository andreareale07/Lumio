import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { useCancelActivity } from "./api";

/** "Interrompi" per un'attivita' in corso (classificazione AI di un import,
 * riclassificazione). Non e' distruttivo: cio' che e' gia' stato classificato
 * resta, il job si ferma da solo tra una transazione e l'altra, quindi non
 * serve una conferma. Dopo il clic dice che l'interruzione e' in corso; il
 * pulsante sparisce da solo quando lo stato diventa "Interrotta". */
export function CancelActivityButton({ cancelUrl }: { cancelUrl: string }) {
  const { t } = useTranslation("activity");
  const cancel = useCancelActivity();
  const [error, setError] = useState<string | null>(null);

  const onCancel = async () => {
    setError(null);
    try {
      await cancel.mutateAsync(cancelUrl);
    } catch (failure) {
      setError(friendlyErrorMessage(failure, t("cancel.error")));
    }
  };

  return (
    <span className="flex flex-wrap items-center gap-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => void onCancel()}
        loading={cancel.isPending}
        disabled={cancel.isSuccess}
      >
        {cancel.isSuccess ? t("cancel.requested") : t("cancel.action")}
      </Button>
      {error && (
        <span role="alert" className="text-xs text-danger">
          {error}
        </span>
      )}
    </span>
  );
}
