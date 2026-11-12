import { useCallback, useState } from "react";
import { Wand2 } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ResponsiveSheet } from "../../components/ui/ResponsiveSheet";
import { useCategories } from "../categories/api";
import { useCategoryLabel } from "../categories/utils";
import type { RuleSuggestion, SuggestionOption } from "../../types/api";
import type { RuleBuilderDefaults } from "./RuleBuilderDialog";
import { RuleImpactSheet } from "./RuleImpact";
import { RuleSentence } from "./RuleSentence";

function optionSummary(t: TFunction<"rules">, option: SuggestionOption): string {
  const total = option.would_change + option.already_correct + option.protected;
  const parts = [
    t("suggestions.nChange", { count: option.would_change }),
    t("suggestions.nOk", { count: option.already_correct }),
    t("suggestions.nProtected", { count: option.protected }),
  ].join(", ");
  return t("suggestions.summary", { count: total, parts });
}

interface RuleSuggestionCardProps {
  suggestion: RuleSuggestion;
  onCreate: (defaults: RuleBuilderDefaults) => void;
}

/** Un suggerimento di regola: la scheda resta compatta (categoria e quante
 * volte) e le proposte, dalla più precisa alla più ampia, si scelgono in un
 * foglio (dal basso su smartphone), cosi' la lista sotto non si sposta. */
export function RuleSuggestionCard({ suggestion, onCreate }: RuleSuggestionCardProps) {
  const { t } = useTranslation("rules");
  const { data: categories } = useCategories();
  const categoryLabel = useCategoryLabel();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [impactOpen, setImpactOpen] = useState(false);
  const closeSheet = useCallback(() => setSheetOpen(false), []);
  const closeImpact = useCallback(() => setImpactOpen(false), []);
  const recommended = suggestion.options.find((option) => option.key === "recommended") ?? suggestion.options[0];
  const [pickedKey, setPickedKey] = useState(recommended?.key);
  const picked: SuggestionOption | undefined =
    suggestion.options.find((option) => option.key === pickedKey) ?? recommended;
  const target = categoryLabel(categories, suggestion.category_id);
  if (!picked) return null;
  const total = picked.would_change + picked.already_correct + picked.protected;

  const footer = (
    <>
      {total > 0 && (
        <Button variant="secondary" onClick={() => setImpactOpen(true)}>
          {t("suggestions.see")}
        </Button>
      )}
      <Button
        onClick={() => {
          setSheetOpen(false);
          onCreate({
            conditions: picked.conditions,
            match_mode: picked.match_mode,
            category_id: suggestion.category_id,
          });
        }}
      >
        {t("suggestions.create")}
      </Button>
    </>
  );

  return (
    <Card className="flex items-center justify-between gap-3 border-primary/30 bg-primary/5">
      <p className="flex min-w-0 items-center gap-2 text-sm text-text">
        <Wand2 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0">
          <strong className="font-semibold">{target}</strong>{" "}
          <span className="text-text-muted">· {t("suggestions.times", { count: suggestion.occurrences })}</span>
        </span>
      </p>
      <Button variant="ghost" size="sm" onClick={() => setSheetOpen(true)}>
        {t("suggestions.open")}
      </Button>

      <ResponsiveSheet open={sheetOpen} onClose={closeSheet} title={target} footer={footer}>
        <div className="flex flex-col gap-3 pb-1">
          {suggestion.ambiguous && (
            <p className="rounded-lg bg-surface-hover px-3 py-2 text-xs text-text-muted">{t("suggestions.ambiguous")}</p>
          )}
          <p className="text-sm text-text">{t("suggestions.question")}</p>
          <div role="radiogroup" aria-label={t("suggestions.question")} className="flex flex-col gap-2">
            {suggestion.options.map((option) => {
              const checked = option.key === picked.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  role="radio"
                  aria-checked={checked}
                  onClick={() => setPickedKey(option.key)}
                  className={`flex min-h-11 items-start gap-3 rounded-xl border p-3 text-left ${
                    checked ? "border-primary bg-primary/10" : "border-border bg-surface"
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`mt-1 h-4 w-4 shrink-0 rounded-full border-2 ${
                      checked ? "border-primary bg-primary" : "border-border"
                    }`}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-text">
                      {t(`suggestions.options.${option.key}`)}
                    </span>
                    <RuleSentence conditions={option.conditions} matchMode={option.match_mode} className="!text-xs !text-text-muted" />
                    <span className="block text-xs text-text-muted">{optionSummary(t, option)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </ResponsiveSheet>

      <RuleImpactSheet
        open={impactOpen}
        onClose={closeImpact}
        input={{ conditions: picked.conditions, match_mode: picked.match_mode, category_id: suggestion.category_id }}
        sentence={<RuleSentence conditions={picked.conditions} matchMode={picked.match_mode} categoryName={target} />}
        targetLabel={target}
      />
    </Card>
  );
}
