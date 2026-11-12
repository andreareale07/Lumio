import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { MatchMode, RuleCondition } from "../../types/api";

function amountText(t: ReturnType<typeof useTranslation>["t"], min: string | null, max: string | null): string {
  const show = (value: string | null) => (value ?? "").replace(".", ",").replace(/,00$/, "");
  if (min && max) return t("rules:sentence.amountBetween", { min: show(min), max: show(max) });
  if (min) return t("rules:sentence.amountMin", { min: show(min) });
  return t("rules:sentence.amountMax", { max: show(max) });
}

interface RuleSentenceProps {
  conditions: RuleCondition[];
  matchMode: MatchMode;
  /** Se presente chiude la frase con "assegna <categoria>". */
  categoryName?: string;
  className?: string;
}

/** Una regola scritta come frase ("Se la descrizione contiene «Rata mutuo» e
 * l'importo è tra 450 e 520 €, assegna Rata mutuo."): sostituisce la riga
 * "Campo Operatore valore" che l'utente non sapeva leggere. */
export function RuleSentence({ conditions, matchMode, categoryName, className = "" }: RuleSentenceProps) {
  const { t } = useTranslation("rules");
  if (conditions.length === 0) {
    return <p className={`text-sm text-text-muted ${className}`}>{t("sentence.empty")}</p>;
  }
  const joiner = matchMode === "any" ? t("sentence.any") : t("sentence.all");
  const parts: ReactNode[] = conditions.map((condition, index) => {
    const separator = index > 0 ? ` ${joiner} ` : ` `;
    if (condition.field === "amount") {
      return (
        <span key={index}>
          {separator}
          {amountText(t, condition.min, condition.max)}
        </span>
      );
    }
    const lead =
      condition.field === "description"
        ? t(`sentence.description.${condition.operator}`)
        : t(`sentence.merchant.${condition.operator}`);
    return (
      <span key={index}>
        {separator}
        {lead} <strong className="font-semibold">«{condition.value}»</strong>
      </span>
    );
  });
  return (
    <p className={`text-sm text-text ${className}`}>
      {t("sentence.if")}
      {parts}
      {categoryName !== undefined && (
        <>
          , {t("sentence.then")} <strong className="font-semibold">{categoryName}</strong>
        </>
      )}
      .
    </p>
  );
}
