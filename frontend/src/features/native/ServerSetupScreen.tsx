import { useState } from "react";
import type { FormEvent } from "react";

import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { AppVersion } from "../../components/ui/AppVersion";
import { Input } from "../../components/ui/Input";
import { isInsecureRemote, normalizeServerUrl, saveServerUrl, testServer } from "../../lib/serverConfig";

/** Prima schermata dell'app nativa: a quale server Lumio collegarsi (il tuo,
 * self-hosted). Salva solo se all'indirizzo risponde davvero un server Lumio. */
export function ServerSetupScreen({ onSaved }: { onSaved: () => void }) {
  const { t } = useTranslation("common");
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const check = normalizeServerUrl(value);
    if (!check.ok) {
      setError(t(check.reason === "empty" ? "native.server.empty" : "native.server.invalid"));
      return;
    }
    // http:// verso un host pubblico: si avvisa e serve un secondo tocco.
    if (isInsecureRemote(check.url) && !warning) {
      setWarning(t("native.server.insecure"));
      return;
    }
    setBusy(true);
    const reachable = await testServer(check.url);
    if (!reachable) {
      setBusy(false);
      setError(t("native.server.unreachable"));
      return;
    }
    await saveServerUrl(check.url);
    setBusy(false);
    onSaved();
  };

  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg px-4 pt-[var(--sat)] pb-[var(--sab)]">
      <form
        onSubmit={(e) => void onSubmit(e)}
        noValidate
        className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-border bg-surface p-6 shadow-sm"
      >
        <div className="text-center">
          <h1 className="text-xl font-semibold text-text">{t("native.server.title")}</h1>
          <p className="mt-1 text-sm text-text-muted">{t("native.server.description")}</p>
          <AppVersion className="mt-1" />
        </div>
        <Input
          label={t("native.server.label")}
          type="url"
          inputMode="url"
          autoCapitalize="none"
          autoCorrect="off"
          placeholder="https://lumio.example.com"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setWarning(null);
          }}
          error={error ?? undefined}
        />
        {warning && <p className="text-sm text-warning">{warning}</p>}
        <p className="text-xs text-text-muted">{t("native.server.hint")}</p>
        <Button type="submit" loading={busy} className="w-full">
          {warning ? t("native.server.connectAnyway") : t("native.server.connect")}
        </Button>
      </form>
    </div>
  );
}
