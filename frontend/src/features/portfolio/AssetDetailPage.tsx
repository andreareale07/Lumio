import { useState } from "react";
import { PiggyBank } from "lucide-react";
import { useLocation, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { RangeSelector } from "../../components/charts/RangeSelector";
import { BackLink } from "../../components/ui/BackLink";
import { Badge } from "../../components/ui/Badge";
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
  formatQuantity,
  formatSignedMoney,
  formatTime,
} from "../../lib/format";
import type { AssetProfile, AssetTaxPreview, HistoryPreset, LotBreakdownRow } from "../../types/api";
import { useMarketDataProfiles } from "../settings/market-data/api";
import { AssetTaxCard } from "../tax/AssetTaxCard";
import {
  useAssetProfile,
  useAssets,
  useAssetTaxPreview,
  useAssetValuation,
  useLotBreakdown,
  usePositions,
  usePriceHistory,
} from "./api";
import { distributionPolicyLabel, useAssetTypeLabel } from "./labels";

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
  const lotBreakdown = useLotBreakdown(assetId ?? null);
  const assetProfile = useAssetProfile(assetId ?? null);
  const valuation = useAssetValuation(assetId ?? null, undefined, detailRefetchMs);
  // Prezzo attuale nella STESSA valuta dei singoli acquisti (di norma quella
  // dell'asset, es. EUR per un titolo comprato via Trade Republic anche se
  // quotato dal provider in JPY/USD) — serve alle colonne "Rendimento" della
  // lista Acquisti sotto, un confronto in valute diverse sarebbe scorretto.
  const nativeValuation = useAssetValuation(assetId ?? null, asset?.currency, detailRefetchMs);
  // Prezzo per la colonna "Tasse" (seguito FETTA 2): solo se e' davvero
  // nella valuta dell'asset (stessa condizione di `canValueOpen` dentro
  // `buildMovementLines`) — un prezzo in un'altra valuta non valorizzerebbe
  // correttamente i lotti aperti, meglio nessun prezzo che uno sbagliato.
  const currentPriceForTax =
    nativeValuation.data?.price !== null &&
    nativeValuation.data?.price !== undefined &&
    nativeValuation.data?.currency === asset?.currency
      ? Number(nativeValuation.data.price)
      : null;
  const taxPreview = useAssetTaxPreview(assetId ?? null, currentPriceForTax);

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
            <span className="font-numeric text-lg font-semibold text-text">{formatQuantity(totalQuantity)}</span>
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

      <MovementsList
        isLoading={lotBreakdown.isLoading}
        isError={lotBreakdown.isError}
        onRetry={() => void lotBreakdown.refetch()}
        rows={lotBreakdown.data ?? []}
        currentPrice={nativeValuation.data?.price !== null && nativeValuation.data?.price !== undefined
          ? Number(nativeValuation.data.price)
          : null}
        currentPriceCurrency={nativeValuation.data?.currency ?? null}
        assetCurrency={asset.currency}
        taxPreview={taxPreview.data ?? null}
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

/** Riga di visualizzazione derivata da `LotBreakdownRow` (scomposizione
 * aperto/chiuso) o da un raggruppamento di vendite — mai la riga grezza
 * dell'acquisto: un acquisto gia' venduto (in tutto o in parte) mostra il
 * rendimento REALIZZATO (contro il prezzo vero di vendita), mai quello non
 * realizzato contro il prezzo di oggi (bug reale segnalato dall'utente). */
interface MovementLine {
  key: string;
  kind: "buy-parent" | "buy-open-child" | "buy-closed-child" | "sell";
  indent: boolean;
  date: string;
  // Chiave di ordinamento — per le righe figlie e' la data del PADRE, mai
  // la propria: altrimenti, con piu' acquisti parzialmente chiusi in tempi
  // diversi, un ordinamento globale per data separerebbe una riga figlia
  // dal suo genitore (l'ordinamento e' stabile in JS, l'adiacenza si
  // ottiene solo mantenendo la stessa chiave per l'intero gruppo).
  sortKey: string;
  quantity: number;
  priceLabel: string;
  status: "open" | "closed" | "partial" | null;
  gain: number | null;
  gainPct: number | null;
  // Colonna "Tasse" (seguito FETTA 2): imposta REALE per le righe chiuse,
  // simulazione cumulativa "se vendo oggi" per le righe aperte — `null`
  // significa "non ancora calcolabile" (dati mancanti), mai confuso con
  // `taxExcludedReason` (calcolo impossibile per costruzione: asset non
  // codificato, conto senza regime).
  tax: number | null;
  taxExcludedReason: string | null;
  // Solo righe aperte: posizione (1-based) nell'ordine di consumo fiscale
  // REALE del proprio conto — il valore cumulativo NON segue l'ordine
  // cronologico di acquisto mostrato in tabella quando la giurisdizione usa
  // LIFO (il lotto piu' recente esce per primo), quindi la sequenza si
  // mostra esplicitamente invece di riordinare le righe (che romperebbe il
  // raggruppamento padre/figli di una posizione parzialmente chiusa).
  taxSequence: number | null;
}

/** Trasforma la scomposizione lotto-per-lotto in righe pronte per la UI +
 * i totali realizzato/non realizzato/complessivo (richiesta esplicita
 * dell'utente: "capire se alla fine la posizione e' in gain o in loss"). */
function buildMovementLines(
  rows: LotBreakdownRow[],
  currentPrice: number | null,
  currentPriceCurrency: string | null,
  assetCurrency: string,
  taxPreview: AssetTaxPreview | null,
): {
  lines: MovementLine[];
  totalRealized: number;
  totalUnrealized: number | null;
  totalTaxRealized: number | null;
  totalTaxOpen: number | null;
} {
  const canValueOpen = currentPrice !== null && currentPriceCurrency === assetCurrency;
  const lines: MovementLine[] = [];
  let totalRealized = 0;
  let hasAnyOpenWithoutPrice = false;
  let totalUnrealized = 0;

  const realizedTaxByKey = new Map(
    (taxPreview?.realized ?? []).map((r) => [`${r.lot_transaction_id}:${r.sell_transaction_id}`, r]),
  );
  const openTaxByLot = new Map((taxPreview?.open_cumulative ?? []).map((o) => [o.transaction_id, o]));
  let hasAnyRealizedTaxExcluded = false;
  let totalTaxRealized = 0;

  // Raggruppa le vendite per transazione: una vendita puo' aver chiuso PIU'
  // acquisti diversi (LIFO/FIFO attraversa piu' lotti) — una riga sola per
  // vendita reale, non una per lotto toccato.
  const sellAgg = new Map<
    string,
    { date: string; quantity: number; proceeds: number; gain: number; tax: number; taxExcludedReason: string | null }
  >();
  for (const row of rows) {
    for (const portion of row.closed_portions) {
      const existing = sellAgg.get(portion.sell_transaction_id) ?? {
        date: portion.sell_trade_date,
        quantity: 0,
        proceeds: 0,
        gain: 0,
        tax: 0,
        taxExcludedReason: null,
      };
      existing.quantity += Number(portion.quantity);
      existing.proceeds += Number(portion.proceeds);
      existing.gain += Number(portion.gain_or_loss);
      const portionTax = realizedTaxByKey.get(`${row.transaction_id}:${portion.sell_transaction_id}`);
      if (portionTax?.excluded_reason) existing.taxExcludedReason = portionTax.excluded_reason;
      else if (portionTax) existing.tax += Number(portionTax.tax_due);
      sellAgg.set(portion.sell_transaction_id, existing);
      totalRealized += Number(portion.gain_or_loss);
      if (portionTax?.excluded_reason) hasAnyRealizedTaxExcluded = true;
      else if (portionTax) totalTaxRealized += Number(portionTax.tax_due);
    }
  }

  for (const row of rows) {
    const openQty = Number(row.open_quantity);
    const hasClosed = row.closed_portions.length > 0;
    const status: MovementLine["status"] = !hasClosed ? "open" : openQty > 0 ? "partial" : "closed";

    if (openQty > 0) {
      if (canValueOpen) totalUnrealized += (currentPrice! - Number(row.price)) * openQty;
      else hasAnyOpenWithoutPrice = true;
    }

    const openTax = !hasClosed ? openTaxByLot.get(row.transaction_id) : undefined;
    const singlePortionTax =
      hasClosed && openQty === 0 && row.closed_portions.length === 1
        ? realizedTaxByKey.get(`${row.transaction_id}:${row.closed_portions[0].sell_transaction_id}`)
        : undefined;

    lines.push({
      key: row.transaction_id,
      kind: "buy-parent",
      indent: false,
      date: row.trade_date,
      sortKey: row.trade_date,
      quantity: Number(row.quantity),
      priceLabel: formatMoney(row.price, assetCurrency),
      status,
      // Nessun figlio da mostrare separatamente (mai toccato o interamente
      // chiuso con un'unica vendita): il rendimento vive gia' qui, niente
      // indentazione superflua.
      gain: !hasClosed
        ? openQty > 0 && canValueOpen
          ? (currentPrice! - Number(row.price)) * openQty
          : null
        : openQty === 0 && row.closed_portions.length === 1
          ? Number(row.closed_portions[0].gain_or_loss)
          : null,
      gainPct: !hasClosed
        ? openQty > 0 && canValueOpen && Number(row.price) !== 0
          ? (currentPrice! - Number(row.price)) / Number(row.price)
          : null
        : openQty === 0 && row.closed_portions.length === 1
          ? Number(row.closed_portions[0].gain_or_loss) / Number(row.closed_portions[0].cost_basis)
          : null,
      tax: openTax
        ? openTax.excluded_reason === null
          ? Number(openTax.tax_due)
          : null
        : singlePortionTax && singlePortionTax.excluded_reason === null
          ? Number(singlePortionTax.tax_due)
          : null,
      taxExcludedReason: openTax?.excluded_reason ?? singlePortionTax?.excluded_reason ?? null,
      taxSequence: openTax ? openTax.sequence + 1 : null,
    });

    const needsChildren = hasClosed && (openQty > 0 || row.closed_portions.length > 1);
    if (needsChildren) {
      for (const portion of row.closed_portions) {
        const qty = Number(portion.quantity);
        const portionTax = realizedTaxByKey.get(`${row.transaction_id}:${portion.sell_transaction_id}`);
        lines.push({
          key: `${row.transaction_id}-closed-${portion.sell_transaction_id}`,
          kind: "buy-closed-child",
          indent: true,
          date: portion.sell_trade_date,
          sortKey: row.trade_date,
          quantity: qty,
          priceLabel: formatMoney(Number(portion.proceeds) / qty, assetCurrency),
          status: null,
          gain: Number(portion.gain_or_loss),
          gainPct: Number(portion.gain_or_loss) / Number(portion.cost_basis),
          tax: portionTax && portionTax.excluded_reason === null ? Number(portionTax.tax_due) : null,
          taxExcludedReason: portionTax?.excluded_reason ?? null,
          taxSequence: null,
        });
      }
      if (openQty > 0) {
        const childOpenTax = openTaxByLot.get(row.transaction_id);
        lines.push({
          key: `${row.transaction_id}-open`,
          kind: "buy-open-child",
          indent: true,
          date: row.trade_date,
          sortKey: row.trade_date,
          quantity: openQty,
          priceLabel: canValueOpen ? formatMoney(currentPrice!, assetCurrency) : "—",
          status: null,
          gain: canValueOpen ? (currentPrice! - Number(row.price)) * openQty : null,
          gainPct: canValueOpen && Number(row.price) !== 0 ? (currentPrice! - Number(row.price)) / Number(row.price) : null,
          tax: childOpenTax && childOpenTax.excluded_reason === null ? Number(childOpenTax.tax_due) : null,
          taxExcludedReason: childOpenTax?.excluded_reason ?? null,
          taxSequence: childOpenTax ? childOpenTax.sequence + 1 : null,
        });
      }
    }
  }

  for (const [sellId, agg] of sellAgg) {
    lines.push({
      key: `sell-${sellId}`,
      kind: "sell",
      indent: false,
      date: agg.date,
      sortKey: agg.date,
      quantity: agg.quantity,
      priceLabel: formatMoney(agg.proceeds / agg.quantity, assetCurrency),
      status: null,
      gain: agg.gain,
      gainPct: null,
      tax: agg.taxExcludedReason === null ? agg.tax : null,
      taxExcludedReason: agg.taxExcludedReason,
      taxSequence: null,
    });
  }

  lines.sort((a, b) => a.sortKey.localeCompare(b.sortKey) || (a.indent ? 1 : 0) - (b.indent ? 1 : 0));

  // C'e' posizione aperta ma nessun prezzo per valorizzarla (`open_cumulative`
  // arriva sempre vuoto in questo caso, mai per assenza di lotti aperti) —
  // il totale deve restare "non calcolabile", mai un falso "0,00 €" che
  // suggerirebbe una simulazione riuscita con risultato zero.
  const hasOpenQuantityWithoutPrice = !canValueOpen && rows.some((r) => Number(r.open_quantity) > 0);
  let totalTaxOpen: number | null = null;
  if (taxPreview && !hasOpenQuantityWithoutPrice) {
    const lastByAccount = new Map<string, (typeof taxPreview.open_cumulative)[number]>();
    for (const o of taxPreview.open_cumulative) {
      const current = lastByAccount.get(o.financial_account_id);
      if (!current || o.sequence > current.sequence) lastByAccount.set(o.financial_account_id, o);
    }
    const lastEntries = [...lastByAccount.values()];
    const hasExcluded = lastEntries.some((o) => o.excluded_reason !== null || o.tax_due === null);
    totalTaxOpen = hasExcluded ? null : lastEntries.reduce((sum, o) => sum + Number(o.tax_due), 0);
  }

  return {
    lines,
    totalRealized,
    totalUnrealized: hasAnyOpenWithoutPrice ? null : totalUnrealized,
    totalTaxRealized: hasAnyRealizedTaxExcluded ? null : totalTaxRealized,
    totalTaxOpen,
  };
}

function StatusBadge({ status }: { status: NonNullable<MovementLine["status"]> }) {
  const { t } = useTranslation("portfolio");
  const tone = status === "open" ? "success" : status === "partial" ? "warning" : "neutral";
  return <Badge tone={tone}>{t(`assetDetail.movements.status.${status}`)}</Badge>;
}

function MovementsList({
  isLoading,
  isError,
  onRetry,
  rows,
  currentPrice,
  currentPriceCurrency,
  assetCurrency,
  totals,
  taxPreview,
}: {
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  rows: LotBreakdownRow[];
  currentPrice: number | null;
  currentPriceCurrency: string | null;
  assetCurrency: string;
  totals: PurchasesTotals | null;
  taxPreview: AssetTaxPreview | null;
}) {
  const { t } = useTranslation("portfolio");
  const { t: tTax } = useTranslation("tax");
  const { lines, totalRealized, totalUnrealized, totalTaxRealized, totalTaxOpen } = buildMovementLines(
    rows,
    currentPrice,
    currentPriceCurrency,
    assetCurrency,
    taxPreview,
  );
  const overallTotal = totalUnrealized !== null ? totalRealized + totalUnrealized : null;
  const hasAnyOpenLine = lines.some((l) => l.taxSequence !== null);

  // Chiamata solo per righe indentate (figlie di un acquisto scomposto):
  // le uniche due varianti sono la porzione chiusa e quella ancora aperta.
  function childLineLabel(line: MovementLine): string {
    return line.kind === "buy-closed-child"
      ? t("assetDetail.movements.closedOn", { date: formatDate(line.date) })
      : t("assetDetail.movements.stillHeld");
  }

  // Contenuto della colonna "Tasse": un numero (reale per le righe chiuse,
  // simulato per le aperte), un badge "escluso" (asset non codificato/conto
  // senza regime — mai un numero inventato), o un trattino se non ancora
  // calcolabile (dati fiscali non caricati). Le righe aperte aggiungono la
  // posizione nell'ordine di consumo fiscale, perche' il valore cumulativo
  // non segue l'ordine di acquisto mostrato in tabella quando la
  // giurisdizione usa LIFO.
  function taxCell(line: MovementLine) {
    if (line.taxExcludedReason) {
      return (
        <span className="text-xs text-text-muted">
          {tTax(`lossPocket.excludedReason.${line.taxExcludedReason}`, { defaultValue: line.taxExcludedReason })}
        </span>
      );
    }
    if (line.tax === null) return <span className="text-text-muted">—</span>;
    return (
      <span>
        {formatMoney(line.tax, assetCurrency)}
        {line.taxSequence !== null && (
          <span
            className="ml-1 text-xs text-text-muted"
            title={t("assetDetail.movements.taxSequenceTooltip", { n: line.taxSequence })}
          >
            ({t("assetDetail.movements.taxSequenceShort", { n: line.taxSequence })})
          </span>
        )}
      </span>
    );
  }

  return (
    <Card className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-text">{t("assetDetail.movements.title")}</h3>
      {isLoading && <SkeletonRows rows={3} />}
      {isError && <ErrorState message={t("assetDetail.movements.loadError")} onRetry={onRetry} />}
      {!isLoading && !isError && lines.length === 0 && (
        <p className="text-sm text-text-muted">{t("assetDetail.movements.empty")}</p>
      )}
      {lines.length > 0 && (
        <>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-sm">
              <thead className="text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("assetDetail.purchases.table.date")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("assetDetail.purchases.table.quantity")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("assetDetail.purchases.table.price")}</th>
                  <th className="px-3 py-2 font-medium">{t("assetDetail.movements.statusHeader")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("assetDetail.purchases.table.gain")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("assetDetail.purchases.table.gainPct")}</th>
                  <th className="px-3 py-2 text-right font-medium" title={hasAnyOpenLine ? t("assetDetail.movements.taxLifoNote") : undefined}>
                    {t("assetDetail.movements.taxHeader")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line.key} className="border-t border-border">
                    <td className={`px-3 py-2 text-text ${line.indent ? "pl-6 text-text-muted" : ""}`}>
                      {line.indent ? childLineLabel(line) : formatDate(line.date)}
                    </td>
                    <td className="font-numeric px-3 py-2 text-right text-text-muted">{formatQuantity(line.quantity)}</td>
                    <td className="font-numeric px-3 py-2 text-right text-text-muted">{line.priceLabel}</td>
                    <td className="px-3 py-2">
                      {line.kind === "sell" && <Badge tone="neutral">{t("assetDetail.movements.sellRow")}</Badge>}
                      {line.status && <StatusBadge status={line.status} />}
                      {line.kind === "buy-parent" && line.status === "partial" && (
                        <span className="ml-2 text-xs text-text-muted">{t("assetDetail.movements.seeBelow")}</span>
                      )}
                    </td>
                    <td
                      className={`font-numeric px-3 py-2 text-right ${
                        line.gain === null ? "text-text-muted" : line.gain >= 0 ? "text-success" : "text-danger"
                      }`}
                    >
                      {line.gain !== null ? formatSignedMoney(line.gain, assetCurrency) : "—"}
                    </td>
                    <td
                      className={`font-numeric px-3 py-2 text-right ${
                        line.gainPct === null ? "text-text-muted" : line.gainPct >= 0 ? "text-success" : "text-danger"
                      }`}
                    >
                      {line.gainPct !== null ? formatPercent(line.gainPct, { signed: true }) : "—"}
                    </td>
                    <td className="font-numeric px-3 py-2 text-right text-text">{taxCell(line)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {hasAnyOpenLine && <p className="text-xs text-text-muted">{t("assetDetail.movements.taxLifoNote")}</p>}

          <ul className="flex flex-col gap-2 md:hidden">
            {lines.map((line) => (
              <li
                key={line.key}
                className={`flex flex-col gap-1 rounded-xl border border-border p-3 text-sm ${line.indent ? "ml-4" : ""}`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-text">{line.indent ? childLineLabel(line) : formatDate(line.date)}</span>
                  {line.kind === "sell" && <Badge tone="neutral">{t("assetDetail.movements.sellRow")}</Badge>}
                  {line.status && <StatusBadge status={line.status} />}
                </div>
                <span className="text-text-muted">
                  {formatQuantity(line.quantity)} @ {line.priceLabel}
                </span>
                {(line.gain !== null || line.gainPct !== null) && (
                  <div className="flex items-center justify-between text-xs">
                    <span className={line.gain === null ? "font-numeric text-text-muted" : `font-numeric ${line.gain >= 0 ? "text-success" : "text-danger"}`}>
                      {line.gain !== null ? formatSignedMoney(line.gain, assetCurrency) : "—"}
                    </span>
                    <span className={line.gainPct === null ? "font-numeric text-text-muted" : `font-numeric ${line.gainPct >= 0 ? "text-success" : "text-danger"}`}>
                      {line.gainPct !== null ? formatPercent(line.gainPct, { signed: true }) : "—"}
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-muted">{t("assetDetail.movements.taxHeader")}</span>
                  {taxCell(line)}
                </div>
              </li>
            ))}
          </ul>
          {hasAnyOpenLine && <p className="text-xs text-text-muted md:hidden">{t("assetDetail.movements.taxLifoNote")}</p>}

          <div className="grid grid-cols-3 gap-3 border-t-2 border-border pt-3 text-sm font-bold">
            <div>
              <span className="block text-xs font-medium text-text-muted">{t("assetDetail.movements.totals.realized")}</span>
              <span className={totalRealized >= 0 ? "text-success" : "text-danger"}>
                {formatSignedMoney(totalRealized, assetCurrency)}
              </span>
            </div>
            <div>
              <span className="block text-xs font-medium text-text-muted">{t("assetDetail.movements.totals.unrealized")}</span>
              <span className={totalUnrealized === null ? "text-text-muted" : totalUnrealized >= 0 ? "text-success" : "text-danger"}>
                {totalUnrealized !== null ? formatSignedMoney(totalUnrealized, assetCurrency) : "—"}
              </span>
            </div>
            <div>
              <span className="block text-xs font-medium text-text-muted">{t("assetDetail.movements.totals.overall")}</span>
              <span className={overallTotal === null ? "text-text-muted" : overallTotal >= 0 ? "text-success" : "text-danger"}>
                {overallTotal !== null ? formatSignedMoney(overallTotal, assetCurrency) : "—"}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 border-t border-border pt-3 text-sm font-bold">
            <div>
              <span className="block text-xs font-medium text-text-muted">{t("assetDetail.movements.totals.taxRealized")}</span>
              <span className="text-text">
                {totalTaxRealized !== null ? formatMoney(totalTaxRealized, assetCurrency) : "—"}
              </span>
            </div>
            <div>
              <span className="block text-xs font-medium text-text-muted">{t("assetDetail.movements.totals.taxOpen")}</span>
              <span className="text-text">{totalTaxOpen !== null ? formatMoney(totalTaxOpen, assetCurrency) : "—"}</span>
            </div>
          </div>

          {totals && (
            <div className="grid grid-cols-2 gap-3 border-t border-border pt-3 text-sm text-text-muted md:grid-cols-4">
              <div>
                <span className="block text-xs font-medium">{t("assetDetail.kpi.position")}</span>
                <span className="text-text">
                  {formatMoney(totals.positionValue, totals.currency)}
                  {!totals.hasMarketData && t("assetDetail.purchases.atCostSuffix")}
                </span>
              </div>
              <div>
                <span className="block text-xs font-medium">{t("assetDetail.kpi.quantity")}</span>
                <span className="text-text">{formatQuantity(totals.quantity)}</span>
              </div>
              <div>
                <span className="block text-xs font-medium">{t("assetDetail.kpi.averagePrice")}</span>
                <span className="text-text">{formatMoney(totals.averageCost, totals.currency)}</span>
              </div>
              <div>
                <span className="block text-xs font-medium">{t("assetDetail.kpi.returnLabel")}</span>
                <span className={totals.unrealizedPl >= 0 ? "text-success" : "text-danger"}>
                  {formatSignedMoney(totals.unrealizedPl, totals.currency)}
                  {totals.unrealizedPlPct !== null && ` (${formatPercent(totals.unrealizedPlPct, { signed: true })})`}
                </span>
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
