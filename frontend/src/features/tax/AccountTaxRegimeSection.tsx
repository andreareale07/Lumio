import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { formatDate } from "../../lib/format";
import { useCreateTaxRegimePeriod, useDeleteTaxRegimePeriod, useTaxRegimePeriods, useTaxRuleset } from "./api";
import { useTaxRegimeLabel } from "./labels";
import { TaxCodeBadge } from "./TaxCodeBadge";

/** Periodi di regime fiscale di un conto (SPEC_TAX_REGIME.md FETTA 1) —
 * stesso pattern di forma di `IbanHistorySection` (stesso problema: una
 * collezione temporale, non un campo scalare del form principale). Caso
 * canonico: un conto Trade Republic con due periodi consecutivi
 * (dichiarativo fino al cambio IBAN, amministrato dopo). */
export function AccountTaxRegimeSection({ accountId }: { accountId: string }) {
  const { t } = useTranslation("tax");
  const { data: periods } = useTaxRegimePeriods(accountId);
  const create = useCreateTaxRegimePeriod(accountId);
  const remove = useDeleteTaxRegimePeriod(accountId);
  const regimeLabel = useTaxRegimeLabel();

  const today = new Date().toISOString().slice(0, 10);
  const { data: ruleset } = useTaxRuleset(today);
  const availableRegimes = ruleset?.regimes ?? [];

  const [regimeCode, setRegimeCode] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(today);
  const [error, setError] = useState<string | null>(null);

  const onAdd = async () => {
    setError(null);
    if (!regimeCode) return;
    try {
      await create.mutateAsync({ regime_code: regimeCode, effective_from: effectiveFrom });
    } catch (err) {
      setError(friendlyErrorMessage(err, t("account.regimeSection.addError")));
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-medium text-text">{t("account.regimeSection.title")}</p>
      <p className="text-sm text-text-muted">{t("account.regimeSection.description")}</p>

      {periods && periods.length === 0 && (
        <p className="text-sm text-text-muted">{t("account.regimeSection.noPeriods")}</p>
      )}
      {periods && periods.length > 0 && (
        <ul className="flex flex-col gap-1">
          {periods
            .slice()
            .sort((a, b) => a.effective_from.localeCompare(b.effective_from))
            .map((period) => (
              <li key={period.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="flex items-center gap-2 text-text">
                  <Badge tone="primary">
                    <TaxCodeBadge value={regimeLabel(period.regime_code)} />
                  </Badge>
                  {t("account.regimeSection.effectiveFrom")}: {formatDate(period.effective_from)}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  loading={remove.isPending}
                  onClick={() => remove.mutate(period.id)}
                >
                  {t("account.regimeSection.remove")}
                </Button>
              </li>
            ))}
        </ul>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <Select
          label={t("account.regimeSection.regimeCode")}
          value={regimeCode}
          onChange={(e) => setRegimeCode(e.target.value)}
        >
          <option value="">—</option>
          {availableRegimes.map((r) => (
            <option key={r.code} value={r.code}>
              {regimeLabel(r.code).label}
            </option>
          ))}
        </Select>
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-text" htmlFor="regime-effective-from">
            {t("account.regimeSection.effectiveFrom")}
          </label>
          <input
            id="regime-effective-from"
            type="date"
            className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-text"
            value={effectiveFrom}
            onChange={(e) => setEffectiveFrom(e.target.value)}
          />
        </div>
        <Button type="button" variant="secondary" size="sm" loading={create.isPending} onClick={() => void onAdd()}>
          {t("account.regimeSection.add")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
