import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

/** Pattern back-navigation estratto da `AssetDetailPage`/`PortfolioDetailPage`
 * (era duplicato copia-incolla fra i due, SPEC_FE_REDESIGN §34). Il testo
 * visibile accanto alla freccia è già di per sé l'accessible name richiesto
 * da §35 — non serve un `aria-label` aggiuntivo finché `label` non è vuoto. */
export function BackLink({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="flex items-center gap-1 text-sm text-text-muted hover:text-text">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" /> {label}
    </Link>
  );
}
