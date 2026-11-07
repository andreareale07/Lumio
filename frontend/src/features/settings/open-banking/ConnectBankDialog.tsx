import { useCallback, useMemo, useState } from "react";
import { ArrowLeft, Landmark } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { BottomSheet } from "../../../components/ui/BottomSheet";
import { Dialog } from "../../../components/ui/Dialog";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import { useIsDesktop } from "../../../lib/useIsDesktop";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import { intlLocale } from "../../../lib/format";
import type { BankInstitution } from "../../../types/api";
import { useInstitutions, useStartConnection } from "./api";
import { COUNTRY_CODES } from "./bankStatus";
import { isSafeAuthorizeUrl } from "./safeUrl";

export interface BankChoice {
  name: string;
  country: string;
  maximumConsentDays?: number | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  /** Rinnovo del consenso: parte direttamente dal riepilogo della banca. */
  initialBank?: BankChoice;
}

const DEFAULT_COUNTRY = "IT";
const DEFAULT_CONSENT_DAYS = 180;

function countryName(code: string): string {
  try {
    return new Intl.DisplayNames([intlLocale()], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** Scelta della banca in due passi: elenco (paese + ricerca) e riepilogo con cio'
 * che succedera' PRIMA di lasciare Lumio (linee guida Open Banking: scopo,
 * sola lettura, durata del consenso, revoca). Le credenziali bancarie si
 * inseriscono solo sul sito della banca. */
export function ConnectBankDialog({ open, onClose, initialBank }: Props) {
  const { t } = useTranslation("settings");
  const [country, setCountry] = useState(initialBank?.country ?? DEFAULT_COUNTRY);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<BankChoice | null>(initialBank ?? null);
  const [error, setError] = useState<string | null>(null);
  const institutions = useInstitutions(country, open && selected === null);
  const start = useStartConnection();
  const isDesktop = useIsDesktop();

  const countries = useMemo(
    () =>
      [...COUNTRY_CODES]
        .map((code) => ({ code, name: countryName(code) }))
        .sort((a, b) => (a.code === DEFAULT_COUNTRY ? -1 : b.code === DEFAULT_COUNTRY ? 1 : a.name.localeCompare(b.name))),
    [],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = institutions.data ?? [];
    return needle ? list.filter((bank) => bank.name.toLowerCase().includes(needle)) : list;
  }, [institutions.data, query]);

  // Stabile: `Dialog` rimette il focus sul primo campo ogni volta che cambia
  // l'identita' di `onClose`, il che toglierebbe il focus dalla ricerca mentre si digita.
  const close = useCallback(() => {
    setError(null);
    setQuery("");
    setSelected(initialBank ?? null);
    onClose();
  }, [initialBank, onClose]);

  const pick = (bank: BankInstitution) => {
    setError(null);
    setSelected({ name: bank.name, country: bank.country, maximumConsentDays: bank.maximum_consent_validity_days });
  };

  const goToBank = async () => {
    if (!selected) return;
    setError(null);
    try {
      const { authorize_url } = await start.mutateAsync({
        aspsp_name: selected.name,
        aspsp_country: selected.country,
      });
      if (!isSafeAuthorizeUrl(authorize_url)) {
        setError(t("items.bankConnections.page.connect.startError"));
        return;
      }
      window.location.assign(authorize_url);
    } catch (e) {
      setError(friendlyErrorMessage(e, t("items.bankConnections.page.connect.startError")));
    }
  };

  const days = Math.min(selected?.maximumConsentDays ?? DEFAULT_CONSENT_DAYS, DEFAULT_CONSENT_DAYS);

  const title =
    selected
          ? t("items.bankConnections.page.connect.confirmTitle", { bank: selected.name })
          : t("items.bankConnections.page.connect.title");

  const footer = selected ? (
          <>
            {!initialBank ? (
              <Button variant="secondary" onClick={() => setSelected(null)} className="flex-1 sm:flex-none">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                {t("items.bankConnections.page.connect.back")}
              </Button>
            ) : (
              <Button variant="secondary" onClick={close} className="flex-1 sm:flex-none">
                {t("items.bankConnections.page.connect.cancel")}
              </Button>
            )}
            <Button onClick={() => void goToBank()} loading={start.isPending} className="flex-1 sm:flex-none">
              {t("items.bankConnections.page.connect.go")}
            </Button>
          </>
        ) : undefined;

  const content = (
    <>
      {!selected ? (
        <div className="flex flex-col gap-3">
          <Input
            label={t("items.bankConnections.page.connect.search")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            type="search"
            autoComplete="off"
          />
          <Select
            label={t("items.bankConnections.page.connect.country")}
            value={country}
            onChange={(event) => {
              setCountry(event.target.value);
              setQuery("");
            }}
          >
            {countries.map(({ code, name }) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </Select>

          {institutions.isLoading && <SkeletonRows rows={4} />}
          {institutions.isError && (
            <div role="alert" className="flex flex-col items-start gap-2 text-sm text-danger">
              <p>{friendlyErrorMessage(institutions.error, t("items.bankConnections.page.connect.loadError"))}</p>
              <Button variant="secondary" size="sm" onClick={() => void institutions.refetch()}>
                {t("items.bankConnections.page.connect.retry")}
              </Button>
            </div>
          )}
          {!institutions.isLoading && !institutions.isError && (
            <>
              <p className="text-xs text-text-muted" aria-live="polite">
                {t("items.bankConnections.page.connect.count", { count: filtered.length })}
              </p>
              {filtered.length === 0 ? (
                <p className="text-sm text-text-muted">{t("items.bankConnections.page.connect.noResults")}</p>
              ) : (
                <ul className="-mx-1 max-h-[45dvh] overflow-y-auto md:max-h-72">
                  {filtered.map((bank) => (
                    <li key={`${bank.country}-${bank.name}`}>
                      <button
                        type="button"
                        onClick={() => pick(bank)}
                        className="flex min-h-11 w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-surface-hover"
                      >
                        {bank.logo_url ? (
                          <img
                            src={bank.logo_url}
                            alt=""
                            referrerPolicy="no-referrer"
                            loading="lazy"
                            className="h-6 w-6 shrink-0 rounded object-contain"
                          />
                        ) : (
                          <Landmark className="h-6 w-6 shrink-0 text-text-muted" aria-hidden="true" />
                        )}
                        <span className="min-w-0 flex-1 truncate text-sm text-text">{bank.name}</span>
                        {bank.beta && <Badge tone="warning">{t("items.bankConnections.page.connect.beta")}</Badge>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-3 text-sm text-text-muted">
          <p>{t("items.bankConnections.page.connect.intro")}</p>
          <ul className="list-disc space-y-1.5 pl-5">
            <li>{t("items.bankConnections.page.connect.points.login")}</li>
            <li>{t("items.bankConnections.page.connect.points.readOnly")}</li>
            <li>{t("items.bankConnections.page.connect.points.consent", { days })}</li>
            <li>{t("items.bankConnections.page.connect.points.revoke")}</li>
          </ul>
          {error && (
            <p role="alert" className="text-danger">
              {error}
            </p>
          )}
        </div>
      )}
    </>
  );

  // Smartphone: pannello dal basso (la ricerca resta in alto, l'elenco scorre);
  // desktop: finestra centrata come gli altri dialog di Lumio.
  if (!isDesktop) {
    return (
      <BottomSheet open={open} onClose={close} title={title}>
        <div className="pb-2 pt-3">{content}</div>
        {footer && <div className="mt-4 flex gap-2">{footer}</div>}
      </BottomSheet>
    );
  }
  return (
    <Dialog open={open} onClose={close} title={title} footer={footer}>
      {content}
    </Dialog>
  );
}
