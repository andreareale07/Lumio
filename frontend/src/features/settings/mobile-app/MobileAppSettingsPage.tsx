import { useEffect, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { PAGE_WIDTH_WIDE } from "../../../components/layout/pageWidths";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Select } from "../../../components/ui/Select";
import { api, logoutRequest } from "../../../lib/apiClient";
import {
  LOCK_DELAY_OPTIONS_S,
  getLockDelay,
  isLockEnabled,
  setLockDelay,
  setLockEnabled,
  type LockDelay,
} from "../../../lib/appLockPrefs";
import { authenticateUser, isBiometricAvailable } from "../../../lib/biometric";
import { disablePush, enablePush, isPushEnabledOnDevice } from "../../../lib/push";
import { setPrivacyScreen } from "../../../lib/privacyScreen";
import { clearServerUrl, getServerUrl } from "../../../lib/serverConfig";

interface PushStatus {
  configured: boolean;
  devices: number;
}

/** Impostazioni > App mobile (solo nell'app nativa): server, blocco con
 * biometria, notifiche push. Tutto per dispositivo. */
export function MobileAppSettingsPage() {
  const { t } = useTranslation("settings");
  const [lockOn, setLockOn] = useState(isLockEnabled());
  const [delay, setDelay] = useState<LockDelay>(getLockDelay());
  const [lockMessage, setLockMessage] = useState<string | null>(null);
  const [pushOn, setPushOn] = useState(false);
  const [pushMessage, setPushMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pushStatus = useQuery({ queryKey: ["push", "status"], queryFn: () => api.get<PushStatus>("/push/status") });

  useEffect(() => {
    void isPushEnabledOnDevice().then(setPushOn);
  }, []);

  const toggleLock = async (next: boolean) => {
    setLockMessage(null);
    if (next) {
      // Si attiva solo dopo una prova riuscita: niente blocco "a vuoto" che
      // chiuderebbe fuori l'utente.
      if (!(await isBiometricAvailable())) {
        setLockMessage(t("items.mobileApp.page.lock.unavailable"));
        return;
      }
      const ok = await authenticateUser(t("items.mobileApp.page.lock.confirmPrompt"), t("items.mobileApp.page.lock.cancel"));
      if (!ok) return;
    }
    await setLockEnabled(next);
    await setPrivacyScreen(next);
    setLockOn(next);
  };

  const changeDelay = async (value: LockDelay) => {
    setDelay(value);
    await setLockDelay(value);
  };

  const togglePush = async (next: boolean) => {
    setPushMessage(null);
    setBusy(true);
    try {
      if (next) {
        const result = await enablePush();
        if (result === "enabled") {
          setPushOn(true);
          void pushStatus.refetch();
        } else {
          setPushMessage(t(result === "denied" ? "items.mobileApp.page.push.denied" : "items.mobileApp.page.push.error"));
        }
      } else {
        await disablePush();
        setPushOn(false);
        void pushStatus.refetch();
      }
    } finally {
      setBusy(false);
    }
  };

  const changeServer = async () => {
    if (!window.confirm(t("items.mobileApp.page.server.confirm"))) return;
    await logoutRequest().catch(() => undefined);
    await clearServerUrl();
    window.location.reload();
  };

  const delayLabel = (value: LockDelay) =>
    value === 0
      ? t("items.mobileApp.page.lock.delayNow")
      : t("items.mobileApp.page.lock.delayMinutes", { count: value / 60 });

  return (
    <div className={PAGE_WIDTH_WIDE}>
      <div>
        <h1 className="text-lg font-semibold text-text">{t("items.mobileApp.label")}</h1>
        <p className="text-sm text-text-muted">{t("items.mobileApp.description")}</p>
      </div>

      <Card className="flex flex-col gap-3">
        <h2 className="font-medium text-text">{t("items.mobileApp.page.lock.title")}</h2>
        <p className="text-sm text-text-muted">{t("items.mobileApp.page.lock.description")}</p>
        <label className="flex min-h-11 items-center gap-3 text-sm text-text">
          <input
            type="checkbox"
            className="h-5 w-5"
            checked={lockOn}
            onChange={(e) => void toggleLock(e.target.checked)}
          />
          {t("items.mobileApp.page.lock.enable")}
        </label>
        {lockOn && (
          <Select
            label={t("items.mobileApp.page.lock.delayLabel")}
            value={delay}
            onChange={(e) => void changeDelay(Number(e.target.value) as LockDelay)}
          >
            {LOCK_DELAY_OPTIONS_S.map((value) => (
              <option key={value} value={value}>
                {delayLabel(value)}
              </option>
            ))}
          </Select>
        )}
        {lockMessage && <p className="text-sm text-danger">{lockMessage}</p>}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="font-medium text-text">{t("items.mobileApp.page.push.title")}</h2>
        <p className="text-sm text-text-muted">{t("items.mobileApp.page.push.description")}</p>
        {pushStatus.data && !pushStatus.data.configured ? (
          <p className="text-sm text-text-muted">{t("items.mobileApp.page.push.notConfigured")}</p>
        ) : (
          <label className="flex min-h-11 items-center gap-3 text-sm text-text">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={pushOn}
              disabled={busy}
              onChange={(e) => void togglePush(e.target.checked)}
            />
            {t("items.mobileApp.page.push.enable")}
          </label>
        )}
        {pushMessage && <p className="text-sm text-danger">{pushMessage}</p>}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="font-medium text-text">{t("items.mobileApp.page.server.title")}</h2>
        <p className="break-all text-sm text-text-muted">{getServerUrl()}</p>
        <Button variant="secondary" onClick={() => void changeServer()}>
          {t("items.mobileApp.page.server.change")}
        </Button>
      </Card>
    </div>
  );
}
