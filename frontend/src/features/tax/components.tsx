import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import type { Asset } from "../../types/api";

/** Collega ogni riga al titolo/vendita che l'ha generata (chiarezza
 * richiesta dall'utente in QA: "non capisco chi contribuisce allo
 * zainetto, quale movimento, quale vendita") — link diretto al dettaglio
 * asset, dove l'elenco Acquisti/vendite permette di risalire al singolo
 * movimento. `null` per le aperture manuali (nessun titolo specifico, un
 * saldo aggregato) — mai un trattino silenzioso senza spiegazione.
 * Condiviso tra `TaxLossPocketPage` e `TaxRealizedEventsPage`. */
export function AssetCell({ assetId, assetById }: { assetId: string | null; assetById: Map<string, Asset> }) {
  const { t } = useTranslation("tax");
  if (assetId === null) {
    return <span className="text-text-muted">{t("lossPocket.table.manualEntry")}</span>;
  }
  const asset = assetById.get(assetId);
  // Stessa precedenza di AssetPicker.tsx/AssetDetailPage.tsx: il nome
  // ripulito dal provider prima del symbol/nome grezzo del parser — una
  // tabella con un nome tecnico sopra un filtro con nomi umani sarebbe
  // un'incoerenza nella stessa pagina.
  const label = asset ? (asset.display_name ?? asset.symbol ?? asset.name) : assetId;
  return (
    <Link to={`/investments/assets/${assetId}`} className="font-medium text-primary hover:underline">
      {label}
    </Link>
  );
}

/** Badge distintivo per riga (SPEC_TAX_REGIME.md: "calcolato" vs "inserito
 * dall'utente", mai un numero senza dire da dove viene) — `source` arriva
 * dal backend come stringa libera, non un enum frontend: solo "computed"
 * ha un significato noto (FETTA 2), qualunque altro valore (oggi solo
 * "user_opening") cade nel default onesto. */
export function SourceBadge({ source }: { source: string }) {
  const { t } = useTranslation("tax");
  if (source === "computed") {
    return <Badge tone="primary">{t("lossPocket.table.sourceComputed")}</Badge>;
  }
  return <Badge tone="neutral">{t("lossPocket.table.sourceUserOpening")}</Badge>;
}
