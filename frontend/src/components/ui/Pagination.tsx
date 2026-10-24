import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "./Button";

interface PaginationProps {
  page: number;
  pageCount: number;
  from: number;
  to: number;
  total: number;
  onPageChange: (page: number) => void;
}

/** Barra di impaginazione per elenchi lunghi: dice sempre DOVE si e' ("16-30
 * di 142") oltre a offrire precedente/successiva. Non compare se tutto sta in
 * una pagina, per non aggiungere rumore alle liste corte. */
export function Pagination({ page, pageCount, from, to, total, onPageChange }: PaginationProps) {
  const { t } = useTranslation("common");
  if (pageCount <= 1) return null;

  return (
    <nav aria-label={t("pagination.label")} className="flex flex-wrap items-center justify-between gap-2">
      <p className="font-numeric text-sm text-text-muted" aria-live="polite">
        {t("pagination.range", { from, to, total })}
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label={t("pagination.previous")}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">{t("pagination.previous")}</span>
        </Button>
        <span className="font-numeric text-sm text-text-muted">{t("pagination.page", { page, pages: pageCount })}</span>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pageCount}
          aria-label={t("pagination.next")}
        >
          <span className="hidden sm:inline">{t("pagination.next")}</span>
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </nav>
  );
}
