import { useRegisterSW } from "virtual:pwa-register/react";
import { useTranslation } from "react-i18next";

import { Button } from "../ui/Button";

/** Avvisa quando c'e' una nuova versione dell'app (service worker in attesa):
 * l'aggiornamento si applica solo su richiesta, cosi' non si perde quanto
 * si sta compilando. */
export function UpdateBanner() {
  const { t } = useTranslation("common");
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW();

  if (!needRefresh) return null;

  return (
    <div
      role="status"
      className="fixed inset-x-3 bottom-[calc(4.5rem+var(--sab))] z-50 flex items-center gap-2 rounded-xl border border-border bg-surface p-3 shadow-lg md:inset-x-auto md:bottom-4 md:right-4 md:max-w-sm"
    >
      <p className="min-w-0 flex-1 text-sm text-text">{t("update.available")}</p>
      <Button size="sm" onClick={() => void updateServiceWorker(true)}>
        {t("update.reload")}
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setNeedRefresh(false)}>
        {t("update.later")}
      </Button>
    </div>
  );
}
