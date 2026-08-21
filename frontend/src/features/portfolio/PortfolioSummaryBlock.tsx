import { useMemo, useState } from "react";
import { PiggyBank } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DonutChart } from "../../components/charts/DonutChart";
import { RangeSelector } from "../../components/charts/RangeSelector";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { formatDate, formatMoney, formatPercent, formatSignedMoney } from "../../lib/format";
import { PORTFOLIO_HISTORY_PRESETS, type PortfolioHistoryPreset } from "../../types/api";
import {
  type PortfolioScope,
  usePortfolioAllocation,
  usePortfolioPerformance,
  usePortfolioValuation,
} from "./api";

// Stessa mappatura preset->giorni gia' usata lato backend per lo storico
// prezzi di un singolo asset (`_PRESET_LOOKBACK_DAYS` in assets.py) — qui
// serve solo a calcolare `date_from` per la query, la granularita' dei
// checkpoint (giornaliera/settimanale/mensile) la sceglie il backend
// (`compute_historical_series`) in base all'ampiezza dell'intervallo.
// "Max" non e' davvero illimitato (nessun `date_from=null` supportato
// dall'endpoint): un tetto largo, i checkpoint precedenti alla prima
// transazione risultano semplicemente a zero, mai un errore.
const PORTFOLIO_PRESET_LOOKBACK_DAYS: Record<PortfolioHistoryPreset, number> = {
  "1M": 31,
  "3M": 93,
  "6M": 186,
  "1A": 366,
  "5A": 1830,
  Max: 7305,
};

/** Blocco condiviso (KPI + andamento + composizione) ripetuto IDENTICO ai
 * due livelli del drill-down Investimenti — Panoramica generale (tutti i
 * conti) e dettaglio di un singolo Portfolio (o dello pseudo-scope "Asset
 * senza portfolio"). Un solo componente, non due implementazioni
 * parallele, cosi' i due livelli restano davvero lo stesso template nel
 * tempo (motivo del redesign: coerenza per ripetizione, non per
 * convenzione di naming). Stesso ordine di informazione della pagina
 * elogiata dall'utente (`AssetDetailPage`): quanto vale/rende in cima,
 * come si e' mosso nel tempo, di cosa e' fatto. */
export function PortfolioSummaryBlock({ scope }: { scope: PortfolioScope }) {
  const { t } = useTranslation("portfolio");
  const portfolioId = scope.portfolioId ?? null;
  const unassigned = scope.unassigned ?? false;

  const valuation = usePortfolioValuation(portfolioId, unassigned);
  const allocation = usePortfolioAllocation(portfolioId, unassigned);

  // Gestione temporale analoga a quella gia' offerta in `AssetDetailPage`
  // (stesso `RangeSelector`, un sottoinsieme di preset senza 1G/1S — non
  // esistono quotazioni intraday per un aggregato multi-asset). Nessun
  // `usePeriodNavigator` qui (scrive sugli stessi search params: due
  // controlli temporali sulla stessa pagina si influenzerebbero a vicenda
  // in modo invisibile). Lo storico e' ricostruito dal backend dal libro
  // movimenti + storico prezzi (`compute_historical_series`), non da uno
  // snapshot precalcolato: funziona quindi anche per "Asset senza
  // portfolio", che non ha mai avuto una riga di snapshot propria.
  const [preset, setPreset] = useState<PortfolioHistoryPreset>("6M");
  const dateTo = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const dateFrom = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - PORTFOLIO_PRESET_LOOKBACK_DAYS[preset]);
    return d.toISOString().slice(0, 10);
  }, [preset]);
  const performance = usePortfolioPerformance({
    portfolio_id: portfolioId ?? undefined,
    unassigned,
    date_from: dateFrom,
    date_to: dateTo,
  });

  // Tutti gli hook (incluso questo `useMemo`) PRIMA di ogni return
  // condizionale sotto — mai dopo, altrimenti React vedrebbe un numero
  // diverso di hook tra un render in caricamento e uno con dati (regola
  // degli hook, non solo stile). Niente ri-bucketizzazione qui: il backend
  // sceglie gia' la granularita' (giornaliera/settimanale/mensile) in base
  // al preset scelto — ribucketizzare sempre "un punto al mese" come prima
  // avrebbe reso inutile scegliere "1M" (un solo punto per l'intero mese).
  const points = useMemoHistoryPoints(performance.data?.points ?? []);

  if (valuation.isLoading || allocation.isLoading || performance.isLoading) {
    return <SkeletonRows rows={4} />;
  }
  if (valuation.isError || allocation.isError || performance.isError) {
    return (
      <ErrorState
        message={t("summaryBlock.loadError")}
        onRetry={() => {
          void valuation.refetch();
          void allocation.refetch();
          void performance.refetch();
        }}
      />
    );
  }

  const v = valuation.data!;
  const a = allocation.data!;
  const hasHoldings = v.has_holdings || Number(v.cost_basis) !== 0;

  if (!hasHoldings) {
    return (
      <EmptyState
        icon={PiggyBank}
        title={t("summaryBlock.empty.title")}
        description={t("summaryBlock.empty.description")}
      />
    );
  }

  const marketValue = Number(v.market_value);
  const costBasis = Number(v.cost_basis);
  const unrealizedPl = Number(v.unrealized_pl);
  const unrealizedPlPct = costBasis !== 0 ? unrealizedPl / costBasis : null;
  const realizedPl = Number(v.realized_pl);

  const periodStart = points.length > 0 ? points[0].value : null;
  const periodEnd = points.length > 0 ? points[points.length - 1].value : null;
  const periodChangePct = periodStart !== null && periodStart !== 0 && periodEnd !== null
    ? (periodEnd - periodStart) / periodStart
    : null;

  const hasCurrencyBreakdown = a.by_currency.length > 1;

  return (
    <div className="flex flex-col gap-4">
      {!v.has_market_data && <p className="text-sm text-text-muted">{t("summaryBlock.missingMarketData")}</p>}
      {v.has_missing_fx_rate && <p className="text-sm text-text-muted">{t("summaryBlock.missingFxRate")}</p>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-text">
            {v.has_market_data ? t("summaryBlock.kpi.currentValue") : t("summaryBlock.kpi.costValue")}
          </h3>
          <span className="font-numeric text-lg font-semibold text-text">{formatMoney(marketValue, v.currency)}</span>
        </Card>
        <Card className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-text">{t("summaryBlock.kpi.invested")}</h3>
          <span className="font-numeric text-lg font-semibold text-text">{formatMoney(costBasis, v.currency)}</span>
        </Card>
        <Card className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-text">{t("summaryBlock.kpi.returnLabel")}</h3>
          <div className="flex items-baseline gap-2">
            <span className="font-numeric text-2xl font-semibold text-text">
              {formatSignedMoney(unrealizedPl, v.currency)}
            </span>
            {unrealizedPlPct !== null && (
              <span className={`font-numeric text-sm font-medium ${unrealizedPlPct >= 0 ? "text-success" : "text-danger"}`}>
                {formatPercent(unrealizedPlPct, { signed: true })}
              </span>
            )}
          </div>
        </Card>
        <Card className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-text">{t("summaryBlock.kpi.realizedPl")}</h3>
          <span className="font-numeric text-lg font-semibold text-text">{formatSignedMoney(realizedPl, v.currency)}</span>
          <span className="text-xs text-text-muted">{t("summaryBlock.kpi.realizedPlHint")}</span>
        </Card>
      </div>

      <ChartCard
        title={t("summaryBlock.valueChart.title")}
        action={<RangeSelector value={preset} onChange={setPreset} presets={PORTFOLIO_HISTORY_PRESETS} />}
        empty={points.length === 0}
        emptyState={
          <EmptyState
            icon={PiggyBank}
            title={t("summaryBlock.valueChart.empty.title")}
            description={t("summaryBlock.valueChart.empty.description")}
          />
        }
        tableCaption={t("summaryBlock.valueChart.tableCaption")}
        tableHeaders={t("summaryBlock.valueChart.tableHeaders", { returnObjects: true }) as string[]}
        tableRows={points.map((p) => [p.label, formatMoney(p.value, v.currency)])}
        footer={
          periodChangePct !== null && (
            <p className="text-sm text-text-muted">
              {t("summaryBlock.valueChart.footer", {
                start: formatMoney(periodStart!, v.currency),
                end: formatMoney(periodEnd!, v.currency),
              })}{" "}
              <span className={periodChangePct >= 0 ? "text-success" : "text-danger"}>
                {formatPercent(periodChangePct, { signed: true })}
              </span>
            </p>
          )
        }
      >
        <AreaTrendChart data={points} currency={v.currency} valueLabel={t("summaryBlock.valueChart.valueLabel")} />
      </ChartCard>

      <div className={`grid grid-cols-1 gap-4 ${hasCurrencyBreakdown ? "lg:grid-cols-2" : ""}`}>
        <ChartCard
          title={t("summaryBlock.compositionChart.title")}
          subtitle={t("summaryBlock.compositionChart.byAssetType")}
          dataTable={false}
          empty={a.by_asset_type.length === 0}
          emptyState={<p className="text-sm text-text-muted">{t("summaryBlock.compositionChart.emptyAssetType")}</p>}
          tableCaption={t("summaryBlock.compositionChart.tableCaptionAssetType")}
          tableHeaders={t("summaryBlock.compositionChart.tableHeadersAssetType", { returnObjects: true }) as string[]}
          tableRows={a.by_asset_type.map((item) => [item.label, formatMoney(item.value, a.currency), formatPercent(item.share)])}
        >
          <DonutChart
            currency={a.currency}
            legend="side"
            data={a.by_asset_type.map((item) => ({ key: item.key, label: item.label, value: Number(item.value), share: item.share }))}
          />
        </ChartCard>

        {hasCurrencyBreakdown && (
          <ChartCard
            title={t("summaryBlock.compositionChart.title")}
            subtitle={t("summaryBlock.compositionChart.byCurrency")}
            dataTable={false}
            tableCaption={t("summaryBlock.compositionChart.tableCaptionCurrency")}
            tableHeaders={t("summaryBlock.compositionChart.tableHeadersCurrency", { returnObjects: true }) as string[]}
            tableRows={a.by_currency.map((item) => [item.label, formatMoney(item.value, a.currency), formatPercent(item.share)])}
          >
            <DonutChart
              currency={a.currency}
              legend="side"
              data={a.by_currency.map((item) => ({ key: item.key, label: item.label, value: Number(item.value), share: item.share }))}
            />
          </ChartCard>
        )}
      </div>
    </div>
  );
}

// Il backend sceglie gia' la granularita' (`compute_historical_series`,
// giornaliera/settimanale/mensile in base all'ampiezza del preset scelto):
// qui si mappa soltanto al formato del grafico, senza ri-bucketizzare.
function useMemoHistoryPoints(points: { snapshot_date: string; market_value: string }[]) {
  return useMemo(
    () =>
      points.map((p) => ({
        period: p.snapshot_date,
        label: formatDate(p.snapshot_date),
        value: Number(p.market_value),
      })),
    [points],
  );
}
