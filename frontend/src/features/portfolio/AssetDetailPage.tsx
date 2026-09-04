import { useState } from "react";
import { PiggyBank } from "lucide-react";
import { useLocation, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { RangeSelector } from "../../components/charts/RangeSelector";
import { BackLink } from "../../components/ui/BackLink";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { SkeletonRows } from "../../components/ui/Skeleton";
import {
  formatDate,
  formatDateTime,
  formatLargeMoney,
  formatMoney,
  formatPercent,
  formatSignedMoney,
  formatTime,
} from "../../lib/format";
import type { AssetProfile, HistoryPreset } from "../../types/api";
import { useMarketDataProfiles } from "../settings/market-data/api";
import { AssetTaxCard } from "../tax/AssetTaxCard";
import {
  useAssetProfile,
  useAssets,
  useAssetValuation,
  useInvestmentTransactions,
  usePositions,
  usePriceHistory,
} from "./api";
import { distributionPolicyLabel, useAssetTypeLabel, useInvestmentTransactionTypeLabel } from "./labels";

export function AssetDetailPage() {
  const { t } = useTranslation("portfolio");
  const assetTypeLabel = useAssetTypeLabel();
  const { assetId } = useParams<{ assetId: string }>();
  const location = useLocation();
  // Un asset si raggiunge da piu' ambiti diversi (Panoramica generale, un
  // Portfolio, "Asset senza portfolio") — mai una singola route "padre"
  // fissa: il link indietro torna a dove si veniva davvero, passato via
  // `state` di navigazione da chi ha linkato qui (vedi PortfolioDetailPage),
  // con "Investimenti" come fallback per un accesso diretto (bookmark,
  // refresh, link condiviso — `state` non sopravvive a nessuno dei due).
  const backTo = (location.state as { from?: string; label?: string } | null)?.from ?? "/investments";
  const backLabel = (location.state as { from?: string; label?: string } | null)?.label ?? t("assetDetail.backFallback");
  const [preset, setPreset] = useState<HistoryPreset>("3M");

  const { data: assets, isLoading, isError, refetch } = useAssets();
  const asset = assets?.find((a) => a.id === assetId);
  const positions = usePositions({ asset_id: assetId, only_open: false });
  // docs/SPEC_STOCK_PRICE.md: mentre questa pagina resta aperta, prezzo e
  // grafico "1G" si aggiornano alla cadenza configurata sul profilo attivo
  // (`detail_refresh_interval_seconds`) — il backend serve una live-quote da
  // cache Redis (mai un effetto sul prezzo daily canonico), e per "1G" serve/
  // arricchisce `asset_price_quotes`. Nessun profilo attivo = nessun polling.
  const marketDataProfiles = useMarketDataProfiles();
  const activeProfile = marketDataProfiles.data?.find((p) => p.is_active) ?? null;
  const detailRefetchMs = activeProfile ? activeProfile.detail_refresh_interval_seconds * 1000 : undefined;
  const history = usePriceHistory(assetId ?? null, preset, preset === "1G" ? detailRefetchMs : undefined);
  const purchases = useInvestmentTransactions({ asset_id: assetId, type: "buy", limit: 100 });
  const assetProfile = useAssetProfile(assetId ?? null);
  const valuation = useAssetValuation(assetId ?? null, undefined, detailRefetchMs);
  // Prezzo attuale nella STESSA valuta dei singoli acquisti (di norma quella
  // dell'asset, es. EUR per un titolo comprato via Trade Republic anche se
  // quotato dal provider in JPY/USD) — serve alle colonne "Rendimento" della
  // lista Acquisti sotto, un confronto in valute diverse sarebbe scorretto.
  const nativeValuation = useAssetValuation(assetId ?? null, asset?.currency, detailRefetchMs);

  if (isLoading) return <SkeletonRows rows={4} />;
  if (isError) {
    return <ErrorState message={t("assetDetail.loadError")} onRetry={() => void refetch()} />;
  }
  if (!asset || !assetId) {
    return (
      <EmptyState
        icon={PiggyBank}
        title={t("assetDetail.notFound.title")}
        description={t("assetDetail.notFound.description")}
        action={
          <LinkButton to="/investments" size="sm">
            {t("assetDetail.notFound.action")}
          </LinkButton>
        }
      />
    );
  }

  const openPositions = (positions.data ?? []).filter((p) => Number(p.quantity) !== 0);
  const totalQuantity = openPositions.reduce((sum, p) => sum + Number(p.quantity), 0);
  const costBasisNative = openPositions.reduce((sum, p) => sum + Number(p.quantity) * Number(p.average_cost), 0);
  const averageCost = totalQuantity !== 0 ? costBasisNative / totalQuantity : 0;

  // "Valore di mercato"/"Rendimento"/"P/L realizzato" vengono dal backend
  // (GET /assets/{id}/valuation), mai ricalcolati qui: la conversione tra
  // la valuta del prezzo e quella della posizione richiede un tasso di
  // cambio (fx_rate_service), che solo il backend puo' risolvere — e' un
  // dato che l'utente considera troppo importante per sparire quando le
  // due valute non coincidono (es. ISIN estero quotato in USD/JPY ma
  // comprato in EUR).
  const hasMarketValue = valuation.data?.has_market_data ?? false;
  const unrealizedPl = valuation.data ? Number(valuation.data.unrealized_pl) : null;
  const unrealizedPlBase = valuation.data ? Number(valuation.data.cost_basis) : null;
  const unrealizedPlPct =
    unrealizedPl !== null && unrealizedPlBase !== null && unrealizedPlBase !== 0
      ? unrealizedPl / unrealizedPlBase
      : null;

  // Prezzo attuale e valuta: dallo stesso endpoint di "Valore di mercato"/
  // "Rendimento" (GET /assets/{id}/valuation), mai da una fonte diversa —
  // due numeri diversi per "il prezzo adesso" nella stessa pagina sarebbero
  // piu' confusi di un singolo dato coerente. Mostra il convertito nella
  // valuta base scelta dall'utente (Impostazioni > Valuta) come valore
  // principale; l'originale resta sempre disponibile (mai perso), al
  // passaggio del mouse quando una conversione e' davvero avvenuta.
  const currentPriceNative = valuation.data?.price_native !== null && valuation.data?.price_native !== undefined
    ? Number(valuation.data.price_native)
    : null;
  const nativeCurrency = valuation.data?.price_native_currency ?? null;
  const hasConvertedPrice = valuation.data?.price !== null && valuation.data?.price !== undefined;
  const displayPrice = hasConvertedPrice ? Number(valuation.data!.price) : currentPriceNative;
  const displayCurrency = hasConvertedPrice ? valuation.data!.currency : nativeCurrency ?? asset.currency;
  const nativeTooltip =
    hasConvertedPrice && nativeCurrency && nativeCurrency !== valuation.data!.currency && currentPriceNative !== null
      ? t("assetDetail.originalCurrencyTooltip", { value: formatMoney(currentPriceNative, nativeCurrency) })
      : undefined;

  // Gli intervalli intraday (1G/1S) hanno bisogno dell'ora in etichetta,
  // altrimenti piu' punti dello stesso giorno sarebbero indistinguibili sul
  // grafico (bug osservato in verifica manuale). "1G" e' sempre un solo
  // giorno (oggi): la data ripetuta su ogni tick sarebbe solo rumore,
  // basta l'ora. "1S" (5 giorni) attraversa piu' giorni distinti e resta
  // su data+ora.
  const isIntraday = preset === "1G" || preset === "1S";
  const historyCurrency = history.data?.currency ?? asset.currency;
  const points = (history.data?.points ?? []).map((p) => ({
    period: p.at,
    label: preset === "1G" ? formatTime(p.at) : isIntraday ? formatDateTime(p.at) : formatDate(p.at),
    value: Number(p.price),
  }));

  // Variazione rispetto al periodo selezionato nel grafico (primo punto
  // mostrato -> prezzo attuale, sempre confrontati nella STESSA valuta
  // nativa: un rapporto e' invariante alla conversione solo se entrambi i
  // termini usano la stessa base, mai numeratore convertito e denominatore
  // nativo) — mai calcolata se le due fonti sono in valute diverse.
  const periodStartPrice = points.length > 0 ? points[0].value : null;
  const periodChangePct =
    currentPriceNative !== null &&
    periodStartPrice !== null &&
    periodStartPrice !== 0 &&
    nativeCurrency === historyCurrency
      ? (currentPriceNative - periodStartPrice) / periodStartPrice
      : null;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <BackLink to={backTo} label={backLabel} />
          <h1 className="mt-1 text-lg font-semibold text-text">{asset.display_name ?? asset.name}</h1>
          <p className="text-sm text-text-muted">
            {[asset.symbol, asset.isin, assetTypeLabel(asset.asset_type), asset.currency]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        {displayPrice !== null && (
          <div className="text-right">
            <p className="text-sm text-text-muted">{t("assetDetail.currentPrice")}</p>
            <div className="flex items-baseline justify-end gap-2">
              <span className="font-numeric text-2xl font-semibold text-text" title={nativeTooltip}>
                {formatMoney(displayPrice, displayCurrency)}
              </span>
              {periodChangePct !== null && (
                <span
                  className={`font-numeric text-sm font-medium ${
                    periodChangePct >= 0 ? "text-success" : "text-danger"
                  }`}
                >
                  {formatPercent(periodChangePct, { signed: true })}
                </span>
              )}
            </div>
            {valuation.data?.price_is_live && (
              <p className="text-xs text-text-muted">
                {valuation.data.price_is_stale && valuation.data.price_quoted_at
                  ? t("assetDetail.currentPriceStale", { value: formatDateTime(valuation.data.price_quoted_at) })
                  : t("assetDetail.currentPriceLive")}
              </p>
            )}
          </div>
        )}
      </div>

      <ChartCard
        title={t("assetDetail.priceChart.title")}
        action={<RangeSelector value={preset} onChange={setPreset} />}
        empty={!history.isLoading && (!history.data?.supports_history || points.length === 0)}
        emptyState={
          <EmptyState
            icon={PiggyBank}
            title={
              history.data?.supports_history === false
                ? t("assetDetail.priceChart.noHistory.title")
                : t("assetDetail.priceChart.noDataInRange.title")
            }
            description={
              history.data?.supports_history === false
                ? t("assetDetail.priceChart.noHistory.description")
                : t("assetDetail.priceChart.noDataInRange.description")
            }
          />
        }
        tableCaption={t("assetDetail.priceChart.tableCaption")}
        tableHeaders={t("assetDetail.priceChart.tableHeaders", { returnObjects: true }) as string[]}
        tableRows={points.map((p) => [p.label, formatMoney(p.value, historyCurrency)])}
      >
        {history.isLoading ? (
          <SkeletonRows rows={4} />
        ) : (
          <AreaTrendChart
            data={points}
            currency={historyCurrency}
            valueLabel={t("assetDetail.priceChart.valueLabel")}
            yAxisDomain="tight"
          />
        )}
      </ChartCard>

      {openPositions.length > 0 && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Card className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-text">
              {hasMarketValue ? t("assetDetail.kpi.position") : t("assetDetail.kpi.positionAtCost")}
            </h3>
            <span className="font-numeric text-lg font-semibold text-text">
              {valuation.data ? formatMoney(valuation.data.market_value, valuation.data.currency) : "—"}
            </span>
          </Card>
          <Card className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-text">{t("assetDetail.kpi.quantity")}</h3>
            <span className="font-numeric text-lg font-semibold text-text">{totalQuantity}</span>
          </Card>
          <Card className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-text">{t("assetDetail.kpi.averagePrice")}</h3>
            <span className="font-numeric text-lg font-semibold text-text">
              {formatMoney(averageCost, asset.currency)}
            </span>
          </Card>
          <Card className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-text">{t("assetDetail.kpi.returnLabel")}</h3>
            {unrealizedPl !== null && valuation.data ? (
              <div className="flex items-baseline gap-2">
                <span className="font-numeric text-2xl font-semibold text-text">
                  {formatSignedMoney(unrealizedPl, valuation.data.currency)}
                </span>
                {unrealizedPlPct !== null && (
                  <span
                    className={`font-numeric text-sm font-medium ${
                      unrealizedPlPct >= 0 ? "text-success" : "text-danger"
                    }`}
                  >
                    {formatPercent(unrealizedPlPct, { signed: true })}
                  </span>
                )}
              </div>
            ) : (
              <span className="font-numeric text-lg font-semibold text-text">—</span>
            )}
          </Card>
        </div>
      )}
      {valuation.data && Number(valuation.data.realized_pl) !== 0 && (
        <p className="text-sm text-text-muted">
          {t("assetDetail.realizedPl", {
            value: formatSignedMoney(valuation.data.realized_pl, valuation.data.currency),
          })}
        </p>
      )}

      <PurchasesList
        isLoading={purchases.isLoading}
        isError={purchases.isError}
        onRetry={() => void purchases.refetch()}
        transactions={purchases.data ?? []}
        currentPrice={nativeValuation.data?.price !== null && nativeValuation.data?.price !== undefined
          ? Number(nativeValuation.data.price)
          : null}
        currentPriceCurrency={nativeValuation.data?.currency ?? null}
        totals={
          openPositions.length > 0 && nativeValuation.data
            ? {
                quantity: totalQuantity,
                averageCost,
                currency: nativeValuation.data.currency,
                hasMarketData: nativeValuation.data.has_market_data,
                positionValue: Number(nativeValuation.data.market_value),
                unrealizedPl: Number(nativeValuation.data.unrealized_pl),
                unrealizedPlPct:
                  Number(nativeValuation.data.cost_basis) !== 0
                    ? Number(nativeValuation.data.unrealized_pl) / Number(nativeValuation.data.cost_basis)
                    : null,
              }
            : null
        }
      />

      <AssetInfoCard profile={assetProfile.data} currency={asset.currency} />
      <AssetTaxCard assetId={asset.id} />
    </div>
  );
}

function AssetInfoCard({ profile, currency }: { profile: AssetProfile | undefined; currency: string }) {
  const { t } = useTranslation("portfolio");
  // Arricchimento best-effort (Step 3): ogni riga presente solo se il
  // rispettivo campo non e' `null` — mai "N/A" in vista, e l'intera card
  // sparisce se il provider attivo non ha restituito nulla.
  if (!profile) return null;
  const rows: [string, string][] = [];
  if (profile.issuer) rows.push([t("assetDetail.info.issuer"), profile.issuer]);
  if (profile.category) rows.push([t("assetDetail.info.category"), profile.category]);
  if (profile.aum) rows.push([t("assetDetail.info.fundAum"), formatLargeMoney(profile.aum, currency)]);
  if (profile.distribution_policy) {
    rows.push([t("assetDetail.info.distributionPolicy"), distributionPolicyLabel(t, profile.distribution_policy)]);
  }
  if (rows.length === 0) return null;

  return (
    <Card className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-text">{t("assetDetail.info.title")}</h3>
      <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-2 sm:flex-col sm:items-start sm:gap-0.5">
            <dt className="text-text-muted">{label}</dt>
            <dd className="font-numeric text-text">{value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

interface PurchasesTotals {
  quantity: number;
  averageCost: number;
  currency: string;
  hasMarketData: boolean;
  positionValue: number;
  unrealizedPl: number;
  unrealizedPlPct: number | null;
}

function PurchasesList({
  isLoading,
  isError,
  onRetry,
  transactions,
  currentPrice,
  currentPriceCurrency,
  totals,
}: {
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  transactions: ReturnType<typeof useInvestmentTransactions>["data"];
  currentPrice: number | null;
  currentPriceCurrency: string | null;
  totals: PurchasesTotals | null;
}) {
  const { t } = useTranslation("portfolio");
  const investmentTransactionTypeLabel = useInvestmentTransactionTypeLabel();
  const rows = transactions ?? [];

  // Rendimento per singolo acquisto: confronta il prezzo pagato (in
  // `t.currency`) con il prezzo attuale nella STESSA valuta — mai calcolato
  // se le due valute non coincidono (es. un acquisto storico registrato in
  // una valuta diversa, caso raro ma possibile), stesso principio onesto
  // usato per "Valore di mercato"/"Rendimento" in cima alla pagina.
  function computeGain(t: NonNullable<typeof rows>[number]) {
    const canCompute =
      currentPrice !== null && currentPriceCurrency === t.currency && t.price !== null && Number(t.price) !== 0;
    if (!canCompute) return { gain: null, gainPct: null };
    const gain = (currentPrice! - Number(t.price)) * Number(t.quantity);
    const gainPct = (currentPrice! - Number(t.price)) / Number(t.price);
    return { gain, gainPct };
  }

  return (
    <Card className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-text">{t("assetDetail.purchases.title")}</h3>
      {isLoading && <SkeletonRows rows={3} />}
      {isError && <ErrorState message={t("assetDetail.purchases.loadError")} onRetry={onRetry} />}
      {!isLoading && !isError && rows.length === 0 && (
        <p className="text-sm text-text-muted">{t("assetDetail.purchases.empty")}</p>
      )}
      {rows.length > 0 && (
        <>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-sm">
              <thead className="text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("assetDetail.purchases.table.date")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("assetDetail.purchases.table.quantity")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("assetDetail.purchases.table.price")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("assetDetail.purchases.table.amount")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("assetDetail.purchases.table.gain")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("assetDetail.purchases.table.gainPct")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => {
                  const { gain, gainPct } = computeGain(t);
                  return (
                    <tr key={t.id} className="border-t border-border">
                      <td className="px-3 py-2 text-text">{formatDate(t.trade_date)}</td>
                      <td className="font-numeric px-3 py-2 text-right text-text-muted">{t.quantity ?? "—"}</td>
                      <td className="font-numeric px-3 py-2 text-right text-text-muted">
                        {t.price ? formatMoney(t.price, t.currency) : "—"}
                      </td>
                      <td className="font-numeric px-3 py-2 text-right text-text">
                        {formatSignedMoney(t.amount, t.currency)}
                      </td>
                      <td
                        className={`font-numeric px-3 py-2 text-right ${
                          gain === null ? "text-text-muted" : gain >= 0 ? "text-success" : "text-danger"
                        }`}
                      >
                        {gain !== null ? formatSignedMoney(gain, t.currency) : "—"}
                      </td>
                      <td
                        className={`font-numeric px-3 py-2 text-right ${
                          gainPct === null ? "text-text-muted" : gainPct >= 0 ? "text-success" : "text-danger"
                        }`}
                      >
                        {gainPct !== null ? formatPercent(gainPct, { signed: true }) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              {totals && (
                <tfoot>
                  <tr className="border-t-2 border-border font-bold">
                    <td className="px-3 py-2 text-text">
                      <span className="block text-xs font-medium text-text-muted">{t("assetDetail.kpi.position")}</span>
                      {formatMoney(totals.positionValue, totals.currency)}
                      {!totals.hasMarketData && t("assetDetail.purchases.atCostSuffix")}
                    </td>
                    <td className="font-numeric px-3 py-2 text-right text-text">{totals.quantity}</td>
                    <td className="font-numeric px-3 py-2 text-right text-text">
                      {formatMoney(totals.averageCost, totals.currency)}
                    </td>
                    <td className="px-3 py-2" />
                    <td
                      className={`font-numeric px-3 py-2 text-right ${
                        totals.unrealizedPl >= 0 ? "text-success" : "text-danger"
                      }`}
                    >
                      {formatSignedMoney(totals.unrealizedPl, totals.currency)}
                    </td>
                    <td
                      className={`font-numeric px-3 py-2 text-right ${
                        totals.unrealizedPlPct === null
                          ? "text-text-muted"
                          : totals.unrealizedPlPct >= 0
                            ? "text-success"
                            : "text-danger"
                      }`}
                    >
                      {totals.unrealizedPlPct !== null ? formatPercent(totals.unrealizedPlPct, { signed: true }) : "—"}
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          <ul className="flex flex-col gap-2 md:hidden">
            {rows.map((txn) => {
              const { gain, gainPct } = computeGain(txn);
              return (
                <li key={txn.id} className="flex flex-col gap-1 rounded-xl border border-border p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-text">{formatDate(txn.trade_date)}</span>
                    <span className="font-numeric text-text">{formatSignedMoney(txn.amount, txn.currency)}</span>
                  </div>
                  <span className="text-text-muted">
                    {investmentTransactionTypeLabel(txn.type)}
                    {txn.quantity && ` · ${txn.quantity}`}
                    {txn.price && ` @ ${formatMoney(txn.price, txn.currency)}`}
                  </span>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-muted">{t("assetDetail.purchases.table.gain")}</span>
                    <span className={gain === null ? "font-numeric text-text-muted" : `font-numeric ${gain >= 0 ? "text-success" : "text-danger"}`}>
                      {gain !== null ? formatSignedMoney(gain, txn.currency) : "—"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-muted">{t("assetDetail.purchases.table.gainPct")}</span>
                    <span className={gainPct === null ? "font-numeric text-text-muted" : `font-numeric ${gainPct >= 0 ? "text-success" : "text-danger"}`}>
                      {gainPct !== null ? formatPercent(gainPct, { signed: true }) : "—"}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>

          {totals && (
            <div className="grid grid-cols-2 gap-3 border-t-2 border-border pt-3 text-sm font-bold md:hidden">
              <div>
                <span className="block text-xs font-medium text-text-muted">{t("assetDetail.kpi.position")}</span>
                {formatMoney(totals.positionValue, totals.currency)}
                {!totals.hasMarketData && t("assetDetail.purchases.atCostSuffix")}
              </div>
              <div className="text-right">
                <span className="block text-xs font-medium text-text-muted">{t("assetDetail.kpi.quantity")}</span>
                {totals.quantity}
              </div>
              <div>
                <span className="block text-xs font-medium text-text-muted">{t("assetDetail.kpi.averagePrice")}</span>
                {formatMoney(totals.averageCost, totals.currency)}
              </div>
              <div className={`text-right ${totals.unrealizedPl >= 0 ? "text-success" : "text-danger"}`}>
                <span className="block text-xs font-medium text-text-muted">{t("assetDetail.kpi.returnLabel")}</span>
                {formatSignedMoney(totals.unrealizedPl, totals.currency)}
                {totals.unrealizedPlPct !== null &&
                  ` (${formatPercent(totals.unrealizedPlPct, { signed: true })})`}
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
