import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { Select } from "../../../components/ui/Select";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import { Tabs } from "../../../components/ui/Tabs";
import { formatDate } from "../../../lib/format";
import {
  useDeleteTaxResidence,
  useTaxJurisdictions,
  useTaxResidences,
  useTaxRuleset,
  useUpsertTaxResidence,
} from "../../tax/api";
import { useTaxJurisdictionLabel, useTaxRegimeLabel, useTaxAssetClassLabel } from "../../tax/labels";
import { TaxCodeBadge } from "../../tax/TaxCodeBadge";
import type { WorkspaceTaxResidence } from "../../../types/api";
import { Percent } from "lucide-react";

interface ResidenceInterval {
  id: string;
  fromYear: number;
  toYear: number | null;
  jurisdictionCode: string;
}

/** `workspace_tax_residences` e' append-only per anno di decorrenza (ogni
 * riga vale dal suo anno fino al successivo cambiamento, mai solo per
 * quell'anno esatto — stesso pattern di `financial_account_tax_regimes`):
 * qui si trasforma l'elenco piatto di righe in intervalli leggibili
 * (`2010 → 2014: Italia`), calcolando il `toYear` di ciascuna dalla
 * `fromYear` della riga successiva. */
function toResidenceIntervals(residences: WorkspaceTaxResidence[]): ResidenceInterval[] {
  const sorted = residences.slice().sort((a, b) => a.fiscal_year - b.fiscal_year);
  return sorted
    .map((residence, i) => ({
      id: residence.id,
      fromYear: residence.fiscal_year,
      toYear: sorted[i + 1] ? sorted[i + 1].fiscal_year - 1 : null,
      jurisdictionCode: residence.jurisdiction_code,
    }))
    .reverse();
}

/** `/settings/tax`, due tab (SPEC_TAX_REGIME.md FETTA 1). Granularita'
 * ANNO per la residenza, mai un date picker — suggerirebbe uno split-year
 * che in Italia non esiste (la residenza vale per l'intero anno solare). */
export function TaxSettingsPage() {
  const { t } = useTranslation("tax");
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") ?? "config";
  const setTab = (next: string) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params);
  };
  const TABS = [
    { key: "config", label: t("settings.tabs.config") },
    { key: "rules", label: t("settings.tabs.rules") },
  ];

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <h1 className="text-lg font-semibold text-text">{t("settings.title")}</h1>
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "config" && <TaxResidenceConfigTab />}
      {tab === "rules" && <TaxRulesTab />}
    </div>
  );
}

function TaxResidenceConfigTab() {
  const { t } = useTranslation("tax");
  const { data: residences, isLoading, isError, refetch } = useTaxResidences();
  const { data: jurisdictions } = useTaxJurisdictions();
  const jurisdictionLabel = useTaxJurisdictionLabel();
  const upsert = useUpsertTaxResidence();
  const remove = useDeleteTaxResidence();

  const currentYear = new Date().getFullYear();
  const [newYear, setNewYear] = useState(currentYear);
  const [newJurisdiction, setNewJurisdiction] = useState("IT");

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">{t("settings.config.intro")}</p>

      {isLoading && <SkeletonRows rows={2} />}
      {isError && <ErrorState onRetry={() => void refetch()} />}

      {!isLoading && !isError && residences && residences.length === 0 && (
        <EmptyState
          icon={Percent}
          title={t("settings.config.empty.title")}
          description={t("settings.config.empty.description")}
        />
      )}

      {residences && residences.length > 0 && (
        <div className="flex flex-col gap-2">
          {/* Append-only per anno di decorrenza (SPEC_TAX_REGIME.md): ogni
           * riga vale dal suo anno fino al successivo cambiamento, mostrata
           * come INTERVALLO (2010 → 2014: Italia) — non un elenco
           * anno-per-anno, che suggerirebbe una ridichiarazione necessaria
           * ogni anno quando invece basta impostarla una volta. */}
          {toResidenceIntervals(residences).map((interval) => (
            <Card key={interval.id} className="flex items-center justify-between gap-3">
              <div>
                <p className="font-medium text-text">
                  {interval.toYear ? `${interval.fromYear} → ${interval.toYear}` : `${interval.fromYear} → ${t("settings.config.ongoing")}`}
                </p>
                <p className="text-sm text-text-muted">{jurisdictionLabel(interval.jurisdictionCode).label}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                loading={remove.isPending}
                onClick={() => remove.mutate(interval.fromYear)}
              >
                {t("settings.config.remove")}
              </Button>
            </Card>
          ))}
        </div>
      )}

      <Card className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-text" htmlFor="tax-residence-year">
            {t("settings.config.yearLabel")}
          </label>
          <input
            id="tax-residence-year"
            type="number"
            className="h-10 w-28 rounded-lg border border-border bg-surface px-3 text-sm text-text"
            value={newYear}
            onChange={(e) => setNewYear(Number(e.target.value))}
          />
        </div>
        <Select
          label={t("settings.config.jurisdictionLabel")}
          value={newJurisdiction}
          onChange={(e) => setNewJurisdiction(e.target.value)}
        >
          {(jurisdictions ?? [{ code: "IT", label_key: "" }]).map((j) => (
            <option key={j.code} value={j.code}>
              {jurisdictionLabel(j.code).label}
            </option>
          ))}
        </Select>
        <Button
          loading={upsert.isPending}
          onClick={() => upsert.mutate({ fiscal_year: newYear, jurisdiction_code: newJurisdiction })}
        >
          {t("settings.config.addResidence")}
        </Button>
      </Card>
    </div>
  );
}

function TaxRulesTab() {
  const { t } = useTranslation("tax");
  const today = new Date().toISOString().slice(0, 10);
  const [on, setOn] = useState(today);
  const { data: ruleset, isLoading, isError, refetch } = useTaxRuleset(on);
  const regimeLabel = useTaxRegimeLabel();
  const assetClassLabel = useTaxAssetClassLabel();
  const eventKindLabel = (kind: string) => t(`settings.rules.eventKind.${kind}`, { defaultValue: kind });

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">{t("settings.rules.intro")}</p>
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium text-text" htmlFor="tax-rules-on">
          {t("settings.rules.asOfLabel")}
        </label>
        <input
          id="tax-rules-on"
          type="date"
          className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-text"
          value={on}
          onChange={(e) => setOn(e.target.value)}
        />
      </div>

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState onRetry={() => void refetch()} />}

      {ruleset && (
        <>
          <Card className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold text-text">{t("settings.rules.treatmentsTitle")}</h3>
            {/* Su mobile una tabella con 7 colonne scorrerebbe in orizzontale
             * (SPEC_TAX_REGIME.md: "diventa una lista di frasi, non una
             * tabella che scorre"): lista di card sotto md, tabella sopra. */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead className="text-left text-text-muted">
                  <tr>
                    <th className="px-2 py-1.5 font-medium">{t("settings.rules.table.assetClass")}</th>
                    <th className="px-2 py-1.5 font-medium">{t("settings.rules.table.eventKind")}</th>
                    <th className="px-2 py-1.5 font-medium">{t("settings.rules.table.gainCategory")}</th>
                    <th className="px-2 py-1.5 font-medium">{t("settings.rules.table.lossCategory")}</th>
                    <th className="px-2 py-1.5 text-right font-medium">{t("settings.rules.table.rate")}</th>
                    <th className="px-2 py-1.5 text-right font-medium">{t("settings.rules.table.coefficient")}</th>
                    <th className="px-2 py-1.5 font-medium">{t("settings.rules.table.reference")}</th>
                  </tr>
                </thead>
                <tbody>
                  {ruleset.treatments.map((tr) => (
                    <tr key={`${tr.asset_class}-${tr.event_kind}`} className="border-t border-border align-top">
                      <td className="px-2 py-1.5 text-text">
                        <TaxCodeBadge value={assetClassLabel(tr.asset_class)} />
                      </td>
                      <td className="px-2 py-1.5 text-text-muted">{eventKindLabel(tr.event_kind)}</td>
                      <td className="px-2 py-1.5 text-text-muted">
                        <TaxCodeBadge value={{ label: tr.gain_category, isTranslated: true }} />
                      </td>
                      <td className="px-2 py-1.5 text-text-muted">
                        <TaxCodeBadge value={{ label: tr.loss_category, isTranslated: true }} />
                      </td>
                      <td className="font-numeric px-2 py-1.5 text-right text-text">
                        {tr.status === "codified" ? `${(Number(tr.rate) * 100).toFixed(2)}%` : "—"}
                      </td>
                      <td className="font-numeric px-2 py-1.5 text-right text-text">
                        {tr.status === "codified" ? `${(Number(tr.taxable_coefficient) * 100).toFixed(2)}%` : "—"}
                      </td>
                      <td className="px-2 py-1.5 text-xs text-text-muted">
                        {tr.status === "not_codified" ? t("settings.rules.notCodified") : tr.legal_reference}
                        {tr.assumption && (
                          <div className="mt-1">
                            <Badge tone="warning">{t("settings.rules.assumptionBadge")}</Badge>
                            {tr.assumption_note && (
                              <p className="mt-1 text-text-muted">
                                {t("settings.rules.assumptionNote")} {tr.assumption_note}
                              </p>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="flex flex-col gap-3 md:hidden">
              {ruleset.treatments.map((tr) => (
                <li key={`${tr.asset_class}-${tr.event_kind}`} className="rounded-lg border border-border p-3 text-sm">
                  <p className="font-medium text-text">
                    <TaxCodeBadge value={assetClassLabel(tr.asset_class)} /> · {eventKindLabel(tr.event_kind)}
                  </p>
                  {tr.status === "codified" ? (
                    <p className="mt-1 text-text-muted">
                      {t("settings.rules.table.rate")}: {(Number(tr.rate) * 100).toFixed(2)}%
                      {" · "}
                      {t("settings.rules.table.coefficient")}: {(Number(tr.taxable_coefficient) * 100).toFixed(2)}%
                    </p>
                  ) : (
                    <p className="mt-1 text-text-muted">{t("settings.rules.notCodified")}</p>
                  )}
                  <p className="mt-1 text-xs text-text-muted">{tr.legal_reference}</p>
                  {tr.assumption && (
                    <div className="mt-2">
                      <Badge tone="warning">{t("settings.rules.assumptionBadge")}</Badge>
                      {tr.assumption_note && <p className="mt-1 text-xs text-text-muted">{tr.assumption_note}</p>}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Card>

          <Card className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-text">{t("settings.rules.offsetTitle")}</h3>
            <p className="text-sm text-text-muted">{t("settings.rules.offsetDescription")}</p>
            {ruleset.offset_rules.length === 0 && (
              <p className="text-sm text-text-muted">{t("settings.rules.offsetNone")}</p>
            )}
            <ul className="flex flex-col gap-1 text-sm">
              {ruleset.offset_rules.map((rule, i) => (
                <li key={i} className="text-text">
                  {rule.loss_category} → {rule.gain_category}
                </li>
              ))}
            </ul>
          </Card>

          <Card className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-text">{t("settings.rules.carryForwardTitle")}</h3>
            <p className="text-sm text-text">
              {t("settings.rules.carryForwardYears", { years: ruleset.carry_forward.years })}
            </p>
            {ruleset.carry_forward.assumption && (
              <div>
                <Badge tone="warning">{t("settings.rules.assumptionBadge")}</Badge>
                {ruleset.carry_forward.assumption_note && (
                  <p className="mt-1 text-sm text-text-muted">
                    {t("settings.rules.assumptionNote")} {ruleset.carry_forward.assumption_note}
                  </p>
                )}
              </div>
            )}
          </Card>

          {ruleset.loss_conversions.length > 0 && (
            <Card className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold text-text">{t("settings.rules.conversionsTitle")}</h3>
              <p className="text-sm text-text-muted">{t("settings.rules.conversionsDescription")}</p>
              <ul className="flex flex-col gap-1 text-sm">
                {ruleset.loss_conversions.map((c, i) => (
                  <li key={i} className="text-text">
                    {t("settings.rules.conversionRow", {
                      from: c.formed_from
                        ? `${formatDate(c.formed_from)} → ${formatDate(c.formed_until)}`
                        : `${t("settings.rules.conversionFromStart")} ${formatDate(c.formed_until)}`,
                      coefficient: (Number(c.coefficient) * 100).toFixed(2),
                    })}{" "}
                    <span className="text-xs text-text-muted">({c.legal_reference})</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-text">{t("settings.rules.regimesTitle")}</h3>
            <div className="flex flex-wrap gap-2">
              {ruleset.regimes.map((r) => (
                <Badge key={r.code} tone="primary">
                  <TaxCodeBadge value={regimeLabel(r.code)} />
                </Badge>
              ))}
            </div>
          </Card>

          <Card className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-text">{t("settings.rules.assetClassesTitle")}</h3>
            <div className="flex flex-wrap gap-2">
              {ruleset.asset_classes.map((c) => (
                <Badge key={c.code} tone={c.codified ? "success" : "neutral"}>
                  <TaxCodeBadge value={assetClassLabel(c.code)} />
                  {" · "}
                  {c.codified ? t("settings.rules.codifiedBadge") : t("settings.rules.notCodifiedBadge")}
                </Badge>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
