import { useMemo, useState, type ReactNode } from "react";
import { PiggyBank } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AreaTrendChart } from "../../components/charts/AreaTrendChart";
import { ChartCard } from "../../components/charts/ChartCard";
import { DonutChart } from "../../components/charts/DonutChart";
import { RangeSelector } from "../../components/charts/RangeSelector";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton, SkeletonRows } from "../../components/ui/Skeleton";
import { formatDate, formatMoney, formatPercent, formatSignedMoney } from "../../lib/format";
import { buildDietzReturnSeries, modifiedDietzReturn, type DietzFlow } from "../../lib/modifiedDietz";
import { PORTFOLIO_HISTORY_PRESETS, type InvestmentTransaction, type PortfolioHistoryPreset } from "../../types/api";
import {
  type PortfolioScope,
  useInvestmentTransactions,
  usePortfolioAllocation,
  usePortfolioPerformance,
  usePortfolioValuation,
} from "./api";

// Solo buy/opening (capitale che ENTRA nel portafoglio) e sell (capitale
// che ne ESCE) contano come flusso Modified Dietz — verificato leggendo
// `position_calc.py`: sono gli unici movimenti che spostano valore
// economico sulle posizioni. Esclusi deliberatamente: deposit/withdrawal
// (cassa pura), dividend (Lumio non lo traccia ancora come contributo al
// rendimento delle posizioni — gap preesistente, non risolto qui),
// fee/tax standalone (riducono realized_pl ma non market_value) e
// split/adjustment (nessun movimento di valore reale). Vedi
// `che-poi-se-stiamo-agile-nygaard.md` per il ragionamento completo.
function toDietzFlow(txn: InvestmentTransaction): DietzFlow | null {
  const qty = Number(txn.quantity ?? 0);
  const price = Number(txn.price ?? 0);
  const fees = Number(txn.fees ?? 0);
  const tax = Number(txn.tax ?? 0);
  if (txn.type === "buy" || txn.type === "opening") {
    return { date: txn.trade_date, amount: qty * price + fees + tax };
  }
  if (txn.type === "sell") {
    return { date: txn.trade_date, amount: -(qty * price - fees - tax) };
  }
  return null;
}

function toIsoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Guadagno Modified Dietz per un intervallo qualunque di uno scope di
 * portfolio — usato per l'anno corrente/precedente in KPI, per il badge
 * accanto a "Valore attuale" E per il grafico "Andamento del rendimento"
 * (`returnSeries`, stesso calcolo applicato punto per punto — vedi
 * `buildDietzReturnSeries`): tutti e tre raccontano sempre la stessa
 * storia, perche' sono la stessa funzione pura applicata allo stesso
 * intervallo. A differenza di un semplice "valore fine - valore inizio",
 * netta i flussi di capitale (acquisti/vendite) avvenuti nell'intervallo —
 * un versamento di 3.000€ che porta il portafoglio da 3.000€ a 6.000€ NON
 * e' un guadagno del 100%, e' capitale aggiunto: senza nettare i flussi lo
 * sarebbe sembrato. E se il range scelto parte da prima dell'apertura
 * della posizione (V0=0), la funzione pura `modifiedDietzReturn` sposta da
 * sola l'inizio effettivo alla data del primo flusso — per questo "Max" e
 * "3M" mostrano lo STESSO risultato quando i dati esistono solo negli
 * ultimi 3 mesi, invece di rompersi. `null`/serie vuota se non ci sono
 * dati di valorizzazione in quell'intervallo (mai un errore/0 fuorviante). */
function useDietzGain(portfolioId: string | null, unassigned: boolean, dateFrom: string, dateTo: string) {
  const performance = usePortfolioPerformance({
    portfolio_id: portfolioId ?? undefined,
    unassigned,
    date_from: dateFrom,
    date_to: dateTo,
  });
  const flows = useInvestmentTransactions({
    portfolio_id: portfolioId ?? undefined,
    unassigned,
    date_from: dateFrom,
    date_to: dateTo,
    limit: 500,
  });

  const points = useMemoHistoryPoints(performance.data?.points ?? []);
  const v0 = points.length > 0 ? points[0]!.value : null;
  const v1 = points.length > 0 ? points[points.length - 1]!.value : null;
  const dietzFlows = (flows.data ?? []).map(toDietzFlow).filter((f): f is DietzFlow => f !== null);
  // Nessuna posizione mai esistita in questo intervallo (V0=0 e nessun
  // flusso, es. intervallo precedente al primo investimento): "nessuna
  // attivita'" e' diverso da "guadagno zero" — il badge/KPI deve sparire
  // (`gain: null`), mai mostrare un fuorviante "0,00€" per un intervallo in
  // cui non si e' mai investito nulla (§ piano, "mai un rendimento a caso").
  const hasActivity = v0 !== null && (v0 !== 0 || dietzFlows.length > 0);
  const netFlowTotal = dietzFlows.reduce((sum, f) => sum + f.amount, 0);
  const gain = hasActivity && v1 !== null ? v1 - v0! - netFlowTotal : null;
  const returnPct = hasActivity && v1 !== null ? modifiedDietzReturn(v0!, v1, dietzFlows, dateFrom, dateTo) : null;
  const returnSeries = buildDietzReturnSeries(points, dietzFlows, dateFrom);

  return {
    isLoading: performance.isLoading || flows.isLoading,
    isError: performance.isError || flows.isError,
    gain,
    returnPct,
    returnSeries,
    refetch: () => {
      void performance.refetch();
      void flows.refetch();
    },
  };
}

// Stessa mappatura preset->giorni gia' usata lato backend per lo storico
// prezzi di un singolo asset (`_PRESET_LOOKBACK_DAYS` in assets.py) — qui
// serve solo a calcolare `date_from` per la query, la granularita' dei
// checkpoint (giornaliera/settimanale/mensile) la sceglie il backend
// (`compute_historical_series`) in base all'ampiezza dell'intervallo.
// "Max" non e' davvero illimitato (nessun `date_from=null` supportato
// dall'endpoint): un tetto largo, i checkpoint precedenti alla prima
// transazione risultano semplicemente a zero, mai un errore.
const PORTFOLIO_PRESET_LOOKBACK_DAYS: Record<PortfolioHistoryPreset, number> = {
  "1G": 1,
  "1S": 7,
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
export function PortfolioSummaryBlock({ scope, belowCards }: { scope: PortfolioScope; belowCards?: ReactNode }) {
  const { t } = useTranslation("portfolio");
  const portfolioId = scope.portfolioId ?? null;
  const unassigned = scope.unassigned ?? false;

  const valuation = usePortfolioValuation(portfolioId, unassigned);
  const allocation = usePortfolioAllocation(portfolioId, unassigned);

  // Gestione temporale analoga a quella gia' offerta in `AssetDetailPage`
  // (stesso `RangeSelector`, stesso set completo di preset — vedi il
  // docstring di `PORTFOLIO_HISTORY_PRESETS` sul perche' 1G/1S restano
  // significativi anche senza quotazioni intraday). Nessun
  // `usePeriodNavigator` qui (scrive sugli stessi search params: due
  // controlli temporali sulla stessa pagina si influenzerebbero a vicenda
  // in modo invisibile). Lo storico e' ricostruito dal backend dal libro
  // movimenti + storico prezzi (`compute_historical_series`), non da uno
  // snapshot precalcolato: funziona quindi anche per "Asset senza
  // portfolio", che non ha mai avuto una riga di snapshot propria.
  const [preset, setPreset] = useState<PortfolioHistoryPreset>("6M");
  // Il gain accanto a "Valore attuale" alterna fra percentuale e importo in
  // valuta al click — stesso valore, due formati, mai due sorgenti diverse.
  const [showGainAmount, setShowGainAmount] = useState(false);
  const dateTo = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const dateFrom = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - PORTFOLIO_PRESET_LOOKBACK_DAYS[preset]);
    return d.toISOString().slice(0, 10);
  }, [preset]);

  // "Guadagno nell'anno" (Modified Dietz, SPEC §30 estesa agli
  // Investimenti con la metrica corretta — non la crescita del valore
  // assoluto, che l'utente ha giustamente osservato essere fuorviante se
  // si continuano a versare soldi). Query indipendenti dal blocco
  // principale sopra: un errore/caricamento lento qui non deve bloccare
  // la vista di valore/composizione, che sono il contenuto primario del
  // blocco (§ piano di sessione, "mai un errore o un rendimento a caso").
  const now = useMemo(() => new Date(), []);
  const currentYear = now.getFullYear();
  const yearStart = `${currentYear}-01-01`;
  const yearEnd = toIsoDate(now);
  const previousYear = currentYear - 1;
  const previousYearStart = `${previousYear}-01-01`;
  const previousYearEnd = `${previousYear}-12-31`;
  const yearDietz = useDietzGain(portfolioId, unassigned, yearStart, yearEnd);
  const previousYearDietz = useDietzGain(portfolioId, unassigned, previousYearStart, previousYearEnd);
  // Stesso identico calcolo, applicato al range del `RangeSelector` invece
  // che all'anno civile — alimenta il badge accanto a "Valore attuale".
  const periodDietz = useDietzGain(portfolioId, unassigned, dateFrom, dateTo);

  // `belowCards` va SEMPRE renderizzato, anche nei rami sotto (skeleton,
  // errore, nessuna posizione) — non solo nel corpo principale a fine
  // funzione: e' contenuto indipendente dalla valorizzazione (es. l'elenco
  // Portfolio in `InvestmentsOverviewPage`, che deve restare visibile
  // anche per un workspace senza ancora nessun investimento), non un
  // dettaglio che ha senso solo quando c'e' un valore da mostrare.
  if (valuation.isLoading || allocation.isLoading || periodDietz.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <SkeletonRows rows={4} />
        {belowCards}
      </div>
    );
  }
  if (valuation.isError || allocation.isError || periodDietz.isError) {
    return (
      <div className="flex flex-col gap-4">
        <ErrorState
          message={t("summaryBlock.loadError")}
          onRetry={() => {
            void valuation.refetch();
            void allocation.refetch();
            periodDietz.refetch();
          }}
        />
        {belowCards}
      </div>
    );
  }

  const v = valuation.data!;
  const a = allocation.data!;
  const hasHoldings = v.has_holdings || Number(v.cost_basis) !== 0;

  if (!hasHoldings) {
    return (
      <div className="flex flex-col gap-4">
        <EmptyState
          icon={PiggyBank}
          title={t("summaryBlock.empty.title")}
          description={t("summaryBlock.empty.description")}
        />
        {belowCards}
      </div>
    );
  }

  const marketValue = Number(v.market_value);
  const costBasis = Number(v.cost_basis);
  const realizedPl = Number(v.realized_pl);

  const hasCurrencyBreakdown = a.by_currency.length > 1;

  return (
    <div className="flex flex-col gap-4">
      {!v.has_market_data && <p className="text-sm text-text-muted">{t("summaryBlock.missingMarketData")}</p>}
      {v.has_missing_fx_rate && <p className="text-sm text-text-muted">{t("summaryBlock.missingFxRate")}</p>}

      {/* Valore attuale: stesso stile piatto del prezzo in testata di
          `AssetDetailPage` (niente `<Card>`) — il segno vicino al valore
          segue il range scelto nel grafico sotto (`periodDietz`, stesso
          intervallo di `dateFrom`/`dateTo`): scegliendo "1S" mostra il
          guadagno della settimana. E' un rendimento Modified Dietz, non un
          semplice "fine meno inizio": netta i versamenti/prelievi di
          capitale nell'intervallo, cosi' un acquisto non si traveste da
          guadagno. Cliccabile: alterna fra percentuale e importo in
          valuta, stesso dato in due formati. */}
      <div>
        <p className="text-sm text-text-muted">
          {v.has_market_data ? t("summaryBlock.kpi.currentValue") : t("summaryBlock.kpi.costValue")}
        </p>
        <div className="flex items-baseline gap-2">
          <span className="font-numeric text-2xl font-semibold text-text">{formatMoney(marketValue, v.currency)}</span>
          {!periodDietz.isLoading && !periodDietz.isError && periodDietz.gain !== null && periodDietz.returnPct !== null && (
            <button
              type="button"
              onClick={() => setShowGainAmount((show) => !show)}
              title={t("summaryBlock.kpi.gainToggleHint")}
              className={`font-numeric text-sm font-medium underline decoration-dotted underline-offset-2 hover:opacity-70 ${periodDietz.returnPct >= 0 ? "text-success" : "text-danger"}`}
            >
              {showGainAmount
                ? formatSignedMoney(periodDietz.gain, v.currency)
                : formatPercent(periodDietz.returnPct, { signed: true })}
            </button>
          )}
        </div>
      </div>

      <ChartCard
        title={t("summaryBlock.returnChart.title")}
        action={<RangeSelector value={preset} onChange={setPreset} presets={PORTFOLIO_HISTORY_PRESETS} />}
        empty={periodDietz.returnSeries.length === 0}
        emptyState={
          <EmptyState
            icon={PiggyBank}
            title={t("summaryBlock.returnChart.empty.title")}
            description={t("summaryBlock.returnChart.empty.description")}
          />
        }
        tableCaption={t("summaryBlock.returnChart.tableCaption")}
        tableHeaders={t("summaryBlock.returnChart.tableHeaders", { returnObjects: true }) as string[]}
        tableRows={periodDietz.returnSeries.map((p) => [p.label, formatPercent(p.value, { signed: true })])}
      >
        <AreaTrendChart data={periodDietz.returnSeries} format="percent" valueLabel={t("summaryBlock.returnChart.valueLabel")} />
      </ChartCard>

      {/* Le card restano — "Valore attuale" e' l'unica salita in testata
          sopra il grafico (§ sopra) e porta gia' il gain (rimosso da qui
          per non duplicarlo): Investito/P&L realizzato/Guadagno annuo
          stanno sotto, stesso ordine di `AssetDetailPage` (prezzo in
          testata, poi grafico, poi le card). */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <Card className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-text">{t("summaryBlock.kpi.invested")}</h3>
          <span className="font-numeric text-lg font-semibold text-text">{formatMoney(costBasis, v.currency)}</span>
        </Card>
        <Card className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-text">{t("summaryBlock.kpi.realizedPl")}</h3>
          <span className="font-numeric text-lg font-semibold text-text">{formatSignedMoney(realizedPl, v.currency)}</span>
          <span className="text-xs text-text-muted">{t("summaryBlock.kpi.realizedPlHint")}</span>
        </Card>
        {yearDietz.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          !yearDietz.isError &&
          yearDietz.gain !== null && (
            <Card className="flex flex-col gap-1">
              <h3 className="text-sm font-semibold text-text">{t("summaryBlock.kpi.yearGain", { year: currentYear })}</h3>
              <div className="flex items-baseline gap-2">
                <span className="font-numeric text-lg font-semibold text-text">
                  {formatSignedMoney(yearDietz.gain, v.currency)}
                </span>
                {yearDietz.returnPct !== null && (
                  <span
                    className={`font-numeric text-sm font-medium ${yearDietz.returnPct >= 0 ? "text-success" : "text-danger"}`}
                  >
                    {formatPercent(yearDietz.returnPct, { signed: true })}
                  </span>
                )}
              </div>
              {!previousYearDietz.isLoading && !previousYearDietz.isError && previousYearDietz.returnPct !== null && (
                <span className="text-xs text-text-muted">
                  {t("summaryBlock.kpi.yearGainVsPreviousYear", {
                    value: formatPercent(previousYearDietz.returnPct, { signed: true }),
                  })}
                </span>
              )}
              <span className="text-xs text-text-muted">{t("summaryBlock.kpi.yearGainHint")}</span>
            </Card>
          )
        )}
      </div>

      {belowCards}

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
