import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { App as CapacitorApp } from "@capacitor/app";
import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { logoutRequest } from "../../lib/apiClient";
import { getLockDelay, isLockEnabled } from "../../lib/appLockPrefs";
import { authenticateUser } from "../../lib/biometric";
import { AppVersion } from "../../components/ui/AppVersion";
import { isNativeApp } from "../../lib/platform";
import { setPrivacyScreen } from "../../lib/privacyScreen";

/** Blocco app con biometria (solo nell'app nativa, se attivato in Impostazioni).
 * - Avvio a freddo: i figli non vengono nemmeno montati finche' non si sblocca,
 *   quindi la sessione (refresh token nel Keystore) non viene ripristinata prima.
 * - Rientro dal background oltre il ritardo scelto: una schermata opaca copre
 *   l'app (i figli restano montati, niente stato perso).
 * Se non si riesce a sbloccare c'e' "Esci": cancella la sessione locale. */
export function AppLockProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation("common");
  const active = isNativeApp() && isLockEnabled();
  const [locked, setLocked] = useState(active);
  const [everUnlocked, setEverUnlocked] = useState(!active);
  const backgroundedAt = useRef<number | null>(null);
  const prompting = useRef(false);

  const unlock = useCallback(async () => {
    if (prompting.current) return;
    prompting.current = true;
    const ok = await authenticateUser(t("native.lock.prompt"), t("native.lock.cancel"));
    prompting.current = false;
    if (ok) {
      setLocked(false);
      setEverUnlocked(true);
    }
  }, [t]);

  // Con il blocco attivo l'app non appare nello switcher e non si fa screenshot.
  useEffect(() => {
    void setPrivacyScreen(active);
  }, [active]);

  // Chiede la biometria appena compare la schermata di blocco.
  useEffect(() => {
    if (locked) void unlock();
  }, [locked, unlock]);

  useEffect(() => {
    if (!active) return undefined;
    const handle = CapacitorApp.addListener("appStateChange", ({ isActive }) => {
      if (!isActive) {
        backgroundedAt.current = Date.now();
        return;
      }
      const left = backgroundedAt.current;
      backgroundedAt.current = null;
      if (left !== null && Date.now() - left >= getLockDelay() * 1000) setLocked(true);
    });
    return () => {
      void handle.then((h) => h.remove());
    };
  }, [active]);

  const signOut = async () => {
    await logoutRequest().catch(() => undefined);
    window.location.reload();
  };

  return (
    <>
      {everUnlocked && children}
      {locked && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t("native.lock.title")}
          className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-4 bg-bg px-6 text-center"
        >
          <Lock className="h-10 w-10 text-primary" />
          <h1 className="text-lg font-semibold text-text">{t("native.lock.title")}</h1>
          <AppVersion />
          <div className="flex w-full max-w-xs flex-col gap-2">
            <Button onClick={() => void unlock()}>{t("native.lock.unlock")}</Button>
            <Button variant="ghost" onClick={() => void signOut()}>
              {t("native.lock.signOut")}
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
