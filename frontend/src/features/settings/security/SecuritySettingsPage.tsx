import { useState } from "react";

import { useMutation } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useAuth } from "../../../app/providers/AuthProvider";
import { PAGE_WIDTH_WIDE } from "../../../components/layout/pageWidths";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { api } from "../../../lib/apiClient";
import { friendlyErrorMessage } from "../../../lib/errorMessage";

interface TotpSetup {
  secret: string;
  otpauth_uri: string;
}

/** Impostazioni > Sicurezza: attivazione/disattivazione della 2FA (TOTP).
 * Il segreto si mostra una sola volta, durante l'attivazione; niente QR (nessuna
 * libreria): chiave da copiare o link `otpauth://` che apre l'app di autenticazione. */
export function SecuritySettingsPage() {
  const { t } = useTranslation("settings");
  const { user, refreshUser } = useAuth();
  const enabled = user?.totp_enabled === true;

  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const reset = () => {
    setSetup(null);
    setCode("");
    setPassword("");
    setError(null);
    setCopied(false);
  };

  const start = useMutation({
    mutationFn: () => api.post<TotpSetup>("/auth/totp/setup"),
    onSuccess: (data) => {
      reset();
      setSetup(data);
    },
    onError: (e) => setError(friendlyErrorMessage(e, t("items.security.page.error"))),
  });

  const enable = useMutation({
    mutationFn: () => api.post("/auth/totp/enable", { code }),
    onSuccess: async () => {
      reset();
      await refreshUser();
    },
    onError: () => setError(t("items.security.page.invalidCode")),
  });

  const disable = useMutation({
    mutationFn: () => api.post("/auth/totp/disable", { password, code }),
    onSuccess: async () => {
      reset();
      await refreshUser();
    },
    onError: () => setError(t("items.security.page.invalidDisable")),
  });

  const copySecret = async () => {
    if (!setup) return;
    try {
      await navigator.clipboard.writeText(setup.secret);
      setCopied(true);
    } catch {
      /* clipboard non disponibile: la chiave resta selezionabile a schermo */
    }
  };

  return (
    <div className={PAGE_WIDTH_WIDE}>
      <div>
        <h1 className="text-lg font-semibold text-text">{t("items.security.label")}</h1>
        <p className="text-sm text-text-muted">{t("items.security.description")}</p>
      </div>

      <Card className="flex flex-col gap-4 p-4">
        <div>
          <h2 className="text-base font-semibold text-text">{t("items.security.page.title")}</h2>
          <p className="text-sm text-text-muted">
            {enabled ? t("items.security.page.statusOn") : t("items.security.page.statusOff")}
          </p>
        </div>

        {!enabled && !setup && (
          <Button className="w-full md:w-auto md:self-start" loading={start.isPending} onClick={() => start.mutate()}>
            {t("items.security.page.start")}
          </Button>
        )}

        {!enabled && setup && (
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              setError(null);
              enable.mutate();
            }}
          >
            <p className="text-sm text-text">{t("items.security.page.step1")}</p>
            <div className="flex flex-col gap-2">
              <code className="break-all rounded-lg border border-border bg-surface-hover p-3 font-mono text-sm text-text">
                {setup.secret}
              </code>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Button type="button" variant="secondary" onClick={() => void copySecret()}>
                  <Copy className="h-4 w-4" />
                  {copied ? t("items.security.page.copied") : t("items.security.page.copy")}
                </Button>
                {/* Link otpauth://: sul telefono apre direttamente l'app di autenticazione. */}
                <a
                  href={setup.otpauth_uri}
                  className="inline-flex h-11 items-center justify-center rounded-lg border border-border bg-surface px-4 text-sm font-medium text-text hover:bg-surface-hover md:h-10"
                >
                  {t("items.security.page.openApp")}
                </a>
              </div>
            </div>
            <p className="text-sm text-text">{t("items.security.page.step2")}</p>
            <Input
              label={t("items.security.page.codeLabel")}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
              error={error ?? undefined}
            />
            <div className="grid grid-cols-2 gap-2 md:flex">
              <Button type="submit" loading={enable.isPending} disabled={code.length !== 6}>
                {t("items.security.page.confirm")}
              </Button>
              <Button type="button" variant="ghost" onClick={reset}>
                {t("items.security.page.cancel")}
              </Button>
            </div>
          </form>
        )}

        {enabled && (
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              setError(null);
              disable.mutate();
            }}
          >
            <p className="text-sm text-text-muted">{t("items.security.page.disableHint")}</p>
            <Input
              label={t("items.security.page.passwordLabel")}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <Input
              label={t("items.security.page.codeLabel")}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
              error={error ?? undefined}
            />
            <Button
              type="submit"
              variant="danger"
              className="w-full md:w-auto md:self-start"
              loading={disable.isPending}
              disabled={code.length !== 6 || !password}
            >
              {t("items.security.page.disable")}
            </Button>
          </form>
        )}

        {error && !setup && !enabled && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
      </Card>
    </div>
  );
}
