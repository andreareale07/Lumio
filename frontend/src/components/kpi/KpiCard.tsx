import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";

import { formatMoney, formatPercent, formatSignedMoney } from "../../lib/format";
import { calculatePeriodComparison } from "../../lib/period";
import { clickableRowArrowClasses, clickableRowClasses } from "../../lib/clickableRow";

interface KpiCardProps {
  title: string;
  value: string;
  currency: string;
  previousValue?: string;
  comparisonLabel?: string;
  /** Un aumento e' un buon segnale (Entrate, Cash Flow) o un cattivo segnale
   * (Spese)? Determina il colore della variazione, non la sua direzione. */
  positiveIsGood?: boolean;
  /** Mostra il segno esplicito (+/-) sul valore principale, mai affidato
   * solo al colore (SPEC_FE §66) — per KPI che sono gia' una differenza
   * (Rendimento, Utile realizzato), non un totale assoluto. Default
   * `false`, comportamento invariato per ogni chiamante esistente. */
  signed?: boolean;
  /** Testo neutro mostrato al posto della riga di variazione quando il
   * chiamante decide che una freccia colorata non sarebbe significativa
   * (PHASE 5: mese troppo giovane, scostamento sotto soglia rispetto alla
   * mediana) — ignorato se `previousValue` produce comunque una riga di
   * variazione (`trend !== "flat"`). Nessun impatto sui chiamanti che non
   * lo passano. */
  note?: string;
  /** PHASE 5b (Dashboard come punto d'ingresso): quando presente, l'intera
   * card diventa un link verso la pagina corrispondente invece che un
   * bottone locale — alternativa a `onClick`, mai entrambi sullo stesso
   * chiamante. */
  href?: string;
  onClick?: () => void;
  /** Nasconde la freccina "apre altrove" pur restando cliccabile — per una
   * card come "Debiti" il link verso Patrimonio resta utile ma l'icona non
   * aggiunge nulla (richiesta esplicita dell'utente dopo aver visto la
   * Dashboard dal vivo). Default `false`, nessun impatto sugli altri
   * chiamanti. */
  hideArrow?: boolean;
}

/** KPI piatta (FETTA 0 del redesign Spese/Entrate/Dashboard, sostituisce la
 * versione precedente in `<Card>`): niente sfondo/bordo a riposo, solo
 * titolo → valore → variazione o nota, deciso con l'utente via mockup
 * interattivi prima del codice. Le card cliccabili (`href`/`onClick`)
 * condividono l'affordance hover (`lib/clickableRow.ts`) con le righe
 * cliccabili di Spese/Entrate — un solo pattern, non uno per componente. */
export function KpiCard({
  title,
  value,
  currency,
  previousValue,
  comparisonLabel,
  positiveIsGood = true,
  signed = false,
  note,
  href,
  onClick,
  hideArrow = false,
}: KpiCardProps) {
  const current = Number(value);
  const previous = previousValue !== undefined ? Number(previousValue) : undefined;
  const { change, trend, isGood } = calculatePeriodComparison(current, previous, positiveIsGood);
  const displayValue = signed ? formatSignedMoney(current, currency) : formatMoney(current, currency);
  const showComparison = trend !== "flat" && change !== undefined;
  const isClickable = !!(href || onClick);

  const content = (
    <div className={`relative flex h-full flex-col gap-1 ${isClickable ? clickableRowClasses : ""}`}>
      {isClickable && !hideArrow && (
        <ArrowUpRight className={`absolute right-1 top-1 ${clickableRowArrowClasses}`} aria-hidden="true" />
      )}
      <span className="text-sm text-text-muted">{title}</span>
      <span className="font-numeric text-2xl font-semibold text-text">{displayValue}</span>
      {showComparison ? (
        <div className="flex flex-wrap items-center gap-1 text-sm">
          <span className={`flex items-center gap-0.5 ${isGood ? "text-success" : "text-danger"}`}>
            {trend === "up" ? (
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ArrowDownRight className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {formatPercent(change)}
          </span>
          {comparisonLabel && <span className="text-text-muted">{comparisonLabel}</span>}
        </div>
      ) : (
        note && <div className="text-sm text-text-muted">{note}</div>
      )}
    </div>
  );

  if (href) {
    return (
      <Link to={href} className="block h-full text-left">
        {content}
      </Link>
    );
  }
  if (!onClick) return content;
  return (
    <button type="button" onClick={onClick} className="h-full text-left">
      {content}
    </button>
  );
}
