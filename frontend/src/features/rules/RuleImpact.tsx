import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { BottomSheet } from "../../components/ui/BottomSheet";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Skeleton } from "../../components/ui/Skeleton";
import { useIsDesktop } from "../../lib/useIsDesktop";
import { formatDate, formatSignedMoney } from "../../lib/format";
import { useCategories } from "../categories/api";
import { useCategoryLabel } from "../categories/utils";
import type { ImpactGroup, RulePreview, RulePreviewItem } from "../../types/api";
import { useRulePreview } from "./api";
import { broadWarning, conflictCount, summaryInput, type RuleImpactInput } from "./impact";

const PAGE = 50;
const MAX_LIMIT = 200;
const GROUPS: ImpactGroup[] = ["change", "ok", "protected"];

function firstNonEmptyGroup(preview: RulePreview | undefined): ImpactGroup {
  if (!preview) return "change";
  if (preview.would_change > 0) return "change";
  if (preview.already_correct > 0) return "ok";
  return preview.protected > 0 ? "protected" : "change";
}

/** Tre contatori: cosa cambia, cosa è già giusto, cosa è protetto da una
 * correzione manuale — il numero che dice all'utente se la regola è sicura. */
export function RuleImpactCounters({ preview }: { preview: RulePreview }) {
  const { t } = useTranslation("rules");
  const cells: { group: ImpactGroup; count: number; tone: string }[] = [
    { group: "change", count: preview.would_change, tone: "bg-warning-bg text-warning" },
    { group: "ok", count: preview.already_correct, tone: "bg-success-bg text-success" },
    { group: "protected", count: preview.protected, tone: "bg-surface-hover text-text" },
  ];
  const label = { change: "impact.change", ok: "impact.ok", protected: "impact.protected" } as const;
  return (
    <div className="grid grid-cols-3 gap-2" data-testid="impact-counters">
      {cells.map((cell) => (
        <div key={cell.group} className={`rounded-lg px-3 py-2 ${cell.tone}`}>
          <p className="font-numeric text-xl font-semibold">{cell.count}</p>
          <p className="text-xs text-text-muted">{t(label[cell.group], { count: cell.count })}</p>
        </div>
      ))}
    </div>
  );
}

export function RuleImpactSkeleton() {
  return (
    <div className="grid grid-cols-3 gap-2" aria-hidden="true">
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} className="h-16 w-full" />
      ))}
    </div>
  );
}

/** Avviso di regola troppo ampia o in conflitto con un'altra categoria (anche con
 * movimenti protetti). Se si conosce la parola che distingue i due casi, propone di
 * escluderla con un tocco ("non contiene …"). */
export function RuleImpactWarning({
  preview,
  excludeWord,
  onExclude,
}: {
  preview: RulePreview;
  excludeWord?: string | null;
  onExclude?: (word: string) => void;
}) {
  const { t } = useTranslation("rules");
  const conflicts = conflictCount(preview);
  const broad = broadWarning(preview);
  if (!broad && conflicts === 0) return null;
  const sample = preview.conflict_samples?.[0];
  return (
    <div className="flex gap-2 rounded-lg bg-warning-bg px-3 py-2 text-sm text-text" role="status">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
      <div className="flex min-w-0 flex-col gap-1">
        <p>
          {broad
            ? t("impact.warnBroad", { count: preview.recategorized })
            : t("impact.warnConflict", { count: conflicts })}
        </p>
        {sample && <p className="break-words text-xs text-text-muted">{t("impact.conflictSample", { sample })}</p>}
        {excludeWord && onExclude && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="self-start"
            onClick={() => onExclude(excludeWord)}
          >
            {t("impact.exclude", { word: excludeWord })}
          </Button>
        )}
      </div>
    </div>
  );
}

function Highlighted({ text, spans }: { text: string; spans: [number, number][] }) {
  const parts: React.ReactNode[] = [];
  let position = 0;
  spans.forEach(([start, end], index) => {
    if (start < position) return;
    if (start > position) parts.push(text.slice(position, start));
    parts.push(
      <mark key={index} className="rounded bg-primary/15 px-0.5 text-text">
        {text.slice(start, end)}
      </mark>,
    );
    position = end;
  });
  parts.push(text.slice(position));
  return <>{parts}</>;
}

function ImpactRow({ item, target }: { item: RulePreviewItem; target: string }) {
  const { t } = useTranslation("rules");
  const { data: categories } = useCategories();
  const categoryLabel = useCategoryLabel();
  const current = categoryLabel(categories, item.category_id);
  return (
    <li className="flex flex-col gap-1 px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-3 text-xs text-text-muted">
        <span>{formatDate(item.date)}</span>
        <span className="font-numeric text-sm font-medium text-text">{formatSignedMoney(item.amount, item.currency)}</span>
      </div>
      <p className="break-words text-sm text-text">
        <Highlighted text={item.description} spans={item.spans} />
      </p>
      <p className="flex flex-wrap items-center gap-1.5 text-xs">
        {item.group === "change" ? (
          <>
            <span className="rounded bg-warning-bg px-1.5 py-0.5 text-warning">{current}</span>
            <span aria-hidden="true">→</span>
            <span className="rounded bg-success-bg px-1.5 py-0.5 text-success">{target}</span>
          </>
        ) : (
          <>
            <span className={`rounded px-1.5 py-0.5 ${item.group === "ok" ? "bg-success-bg text-success" : "bg-surface-hover text-text-muted"}`}>
              {current}
            </span>
            <span className="text-text-muted">{item.group === "ok" ? t("impact.rowOk") : t("impact.rowProtected")}</span>
          </>
        )}
      </p>
    </li>
  );
}

interface RuleImpactSheetProps {
  open: boolean;
  onClose: () => void;
  input: RuleImpactInput;
  /** Frase della regola, mostrata in cima: ricorda cosa si sta guardando. */
  sentence: React.ReactNode;
  targetLabel: string;
}

/** Elenco dei movimenti toccati da una regola, diviso nei tre gruppi, con la
 * parte che ha combaciato evidenziata. Bottom sheet su smartphone. */
export function RuleImpactSheet({ open, onClose, input, sentence, targetLabel }: RuleImpactSheetProps) {
  const isDesktop = useIsDesktop();
  const { t } = useTranslation("rules");
  const title = t("impact.title");
  const body = open ? <ImpactBody input={input} sentence={sentence} targetLabel={targetLabel} /> : null;
  if (isDesktop) {
    return (
      <Dialog open={open} onClose={onClose} title={title} size="lg">
        {body}
      </Dialog>
    );
  }
  return (
    <BottomSheet open={open} onClose={onClose} title={title}>
      {body}
    </BottomSheet>
  );
}

function ImpactBody({ input, sentence, targetLabel }: Omit<RuleImpactSheetProps, "open" | "onClose">) {
  const { t } = useTranslation("rules");
  const base = useRulePreview(summaryInput(input));
  const [chosen, setChosen] = useState<ImpactGroup | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const group = chosen ?? firstNonEmptyGroup(base.data);
  const list = useRulePreview({ ...input, group, limit, offset: 0 });
  const counts = base.data;
  const groupCount = (value: ImpactGroup) =>
    counts ? { change: counts.would_change, ok: counts.already_correct, protected: counts.protected }[value] : 0;
  const items = list.data?.items ?? [];
  const canLoadMore = counts !== undefined && items.length < groupCount(group) && limit < MAX_LIMIT;

  return (
    <div className="flex flex-col gap-3 pb-2">
      <div className="rounded-lg bg-surface-hover px-3 py-2">{sentence}</div>
      <div className="grid grid-cols-3 overflow-hidden rounded-lg border border-border" role="group">
        {GROUPS.map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={group === value}
            onClick={() => {
              setChosen(value);
              setLimit(PAGE);
            }}
            className={`min-h-11 border-l border-border px-1 text-xs first:border-l-0 ${
              group === value ? "bg-primary/10 font-semibold text-primary" : "bg-surface text-text"
            }`}
          >
            {t(`impact.groups.${value}`, { count: groupCount(value) })}
          </button>
        ))}
      </div>
      {group === "protected" && <p className="text-xs text-text-muted">{t("impact.protectedHint")}</p>}
      {(base.isError || list.isError) && (
        <p role="alert" className="text-sm text-danger">
          {t("impact.error")}
        </p>
      )}
      {list.isLoading && <Skeleton className="h-40 w-full" />}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <p className="text-sm text-text-muted">{t("impact.emptyGroup")}</p>
      )}
      {items.length > 0 && (
        <ul className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface">
          {items.map((item) => (
            <ImpactRow key={item.id} item={item} target={targetLabel} />
          ))}
        </ul>
      )}
      {canLoadMore && (
        <Button variant="secondary" onClick={() => setLimit((value) => Math.min(MAX_LIMIT, value + PAGE))}>
          {t("impact.loadMore")}
        </Button>
      )}
      {counts?.truncated && <p className="text-xs text-text-muted">{t("impact.truncated")}</p>}
    </div>
  );
}
