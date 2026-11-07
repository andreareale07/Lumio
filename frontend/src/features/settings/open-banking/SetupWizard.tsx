import { useState } from "react";
import { Check, Copy, Download, ExternalLink } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import type { OpenBankingStatus } from "../../../types/api";
import { useGenerateCredentials, useSetApplicationId } from "./api";
import { downloadCertificate } from "./downloadCertificate";

const CONTROL_PANEL_URL = "https://enablebanking.com/cp";
const APPLICATION_ID_PATTERN = /^[A-Za-z0-9._-]{8,100}$/;
const TOTAL_STEPS = 3;

type Step = 1 | 2 | 3;

function CopyField({ value, label, multiline = false }: { value: string; label: string; multiline?: boolean }) {
  const { t } = useTranslation("settings");
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard non disponibile (contesto non sicuro): si copia a mano dal riquadro.
    }
  };
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-text">{label}</span>
      <div className="flex flex-col gap-2 rounded-md border border-border bg-surface-hover p-2 sm:flex-row sm:items-start">
        {multiline ? (
          <textarea
            readOnly
            aria-label={label}
            value={value}
            rows={4}
            className="min-w-0 flex-1 resize-none bg-transparent font-mono text-xs text-text"
          />
        ) : (
          <code className="min-w-0 flex-1 break-all py-1.5 font-mono text-xs text-text">{value}</code>
        )}
        <Button type="button" variant="secondary" size="sm" onClick={() => void copy()} className="self-start">
          {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
          {copied ? t("items.bankConnections.page.setup.copied") : t("items.bankConnections.page.setup.copy")}
        </Button>
      </div>
    </div>
  );
}

/** Configurazione guidata in 3 schermate, una per passo, con barra di
 * avanzamento. L'utente registra la PROPRIA applicazione su Enable Banking (i
 * Terms del provider vietano credenziali condivise): Lumio genera la chiave
 * (che resta sul server), l'utente carica il certificato e incolla l'application
 * ID ricevuto. */
export function SetupWizard({ status }: { status: OpenBankingStatus }) {
  const { t } = useTranslation("settings");
  const generate = useGenerateCredentials();
  const saveApplicationId = useSetApplicationId();
  const credential = status.credential;
  // Chi ha gia' generato il certificato riparte dal passo 2.
  const [step, setStep] = useState<Step>(credential ? 2 : 1);
  const [applicationId, setApplicationId] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const emphasis = {
    strong: <strong className="text-text" />,
    code: <code className="rounded bg-surface-hover px-1 py-0.5 font-mono text-xs" />,
  };
  const stepTitle = t(`items.bankConnections.page.setup.step${step}.title`);

  const onGenerate = async () => {
    setActionError(null);
    try {
      await generate.mutateAsync();
    } catch (error) {
      setActionError(friendlyErrorMessage(error, t("items.bankConnections.page.setup.step1.error")));
    }
  };

  const onSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = applicationId.trim();
    if (!APPLICATION_ID_PATTERN.test(value)) {
      setFieldError(t("items.bankConnections.page.setup.step3.invalid"));
      return;
    }
    setFieldError(null);
    setActionError(null);
    try {
      await saveApplicationId.mutateAsync(value);
    } catch (error) {
      setActionError(friendlyErrorMessage(error, t("items.bankConnections.page.setup.step3.error")));
    }
  };

  const back = (
    <Button type="button" variant="secondary" onClick={() => setStep((step - 1) as Step)}>
      {t("items.bankConnections.page.setup.back")}
    </Button>
  );

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
          {t("items.bankConnections.page.setup.stepLabel", { current: step, total: TOTAL_STEPS })}
        </p>
        <div
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={TOTAL_STEPS}
          aria-valuenow={step}
          aria-label={t("items.bankConnections.page.setup.title")}
          className="mt-2 h-1 overflow-hidden rounded-full bg-surface-hover"
        >
          <div className="h-full bg-text transition-all" style={{ width: `${(step / TOTAL_STEPS) * 100}%` }} />
        </div>
      </div>

      <div>
        <h2 className="text-base font-semibold text-text">{stepTitle}</h2>
        {step === 1 && (
          <p className="text-sm text-text-muted">{t("items.bankConnections.page.setup.description")}</p>
        )}
      </div>

      {step === 1 && (
        <section className="flex flex-col gap-3">
          <p className="text-sm text-text-muted">{t("items.bankConnections.page.setup.step1.description")}</p>
          {!credential ? (
            <Button onClick={() => void onGenerate()} loading={generate.isPending} className="w-full sm:w-auto sm:self-start">
              {t("items.bankConnections.page.setup.step1.generate")}
            </Button>
          ) : (
            <>
              <CopyField
                value={credential.certificate_pem}
                label={t("items.bankConnections.page.setup.step1.certificateLabel")}
                multiline
              />
              <Button
                type="button"
                variant="secondary"
                onClick={() => downloadCertificate(credential.certificate_pem)}
                className="w-full sm:w-auto sm:self-start"
              >
                <Download className="h-4 w-4" aria-hidden="true" />
                {t("items.bankConnections.page.setup.step1.download")}
              </Button>
              <Button type="button" onClick={() => setStep(2)} className="w-full">
                {t("items.bankConnections.page.setup.next")}
              </Button>
            </>
          )}
        </section>
      )}

      {step === 2 && (
        <section className="flex flex-col gap-3">
          <ol className="list-decimal space-y-2 pl-5 text-sm text-text-muted">
            <li>
              <Trans t={t} i18nKey="items.bankConnections.page.setup.step2.createAccount" components={emphasis} />
            </li>
            <li>
              <Trans t={t} i18nKey="items.bankConnections.page.setup.step2.registerApp" components={emphasis} />
            </li>
            <li>
              <Trans t={t} i18nKey="items.bankConnections.page.setup.step2.uploadCertificate" components={emphasis} />
            </li>
            <li>
              <Trans t={t} i18nKey="items.bankConnections.page.setup.step2.redirectUrl" components={emphasis} />
            </li>
            <li>
              <Trans t={t} i18nKey="items.bankConnections.page.setup.step2.linkAccounts" components={emphasis} />
            </li>
          </ol>
          <CopyField value={status.redirect_uri} label={t("items.bankConnections.page.setup.step2.redirectLabel")} />
          <a
            href={CONTROL_PANEL_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center gap-1.5 font-medium text-primary hover:underline md:min-h-0"
          >
            {t("items.bankConnections.page.setup.step2.openPanel")}
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
          <div className="grid grid-cols-2 gap-2">
            {back}
            <Button type="button" onClick={() => setStep(3)}>
              {t("items.bankConnections.page.setup.done")}
            </Button>
          </div>
        </section>
      )}

      {step === 3 && (
        <form onSubmit={(event) => void onSave(event)} className="flex flex-col gap-3" noValidate>
          <p className="text-sm text-text-muted">{t("items.bankConnections.page.setup.step3.description")}</p>
          <Input
            label={t("items.bankConnections.page.setup.step3.label")}
            value={applicationId}
            onChange={(event) => setApplicationId(event.target.value)}
            placeholder={t("items.bankConnections.page.setup.step3.placeholder")}
            error={fieldError ?? undefined}
            autoComplete="off"
            spellCheck={false}
          />
          <div className="grid grid-cols-2 gap-2">
            {back}
            <Button type="submit" loading={saveApplicationId.isPending}>
              {t("items.bankConnections.page.setup.step3.save")}
            </Button>
          </div>
        </form>
      )}

      {actionError && (
        <p role="alert" className="text-sm text-danger">
          {actionError}
        </p>
      )}
    </Card>
  );
}
