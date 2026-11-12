import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Wand2, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { ResponsiveSheet } from "../../components/ui/ResponsiveSheet";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { CategoryPicker } from "../categories/CategoryPicker";
import { useCategories } from "../categories/api";
import { useCategoryLabel } from "../categories/utils";
import { ApiError } from "../../lib/apiClient";
import type { AmountCondition, MatchMode, Rule, RuleCondition, TextCondition, Transaction } from "../../types/api";
import { useCreateRule, useRulePreview, useTriggerReclassification, useUpdateRule } from "./api";
import {
  MAX_CONDITIONS,
  autoRuleName,
  conditionsToSelection,
  defaultSelection,
  exclusionWord,
  emptyAmountCondition,
  emptyTextCondition,
  hasInvalidCondition,
  normalizeConditions,
  selectionToConditions,
  stableTokenIndexes,
  tokenizeDescription,
  validateCondition,
  type ConditionError,
} from "./conditions";
import { summaryInput, type RuleImpactInput } from "./impact";
import { RuleImpactCounters, RuleImpactSheet, RuleImpactSkeleton, RuleImpactWarning } from "./RuleImpact";
import { RuleSentence } from "./RuleSentence";

export interface RuleBuilderDefaults {
  conditions?: RuleCondition[];
  match_mode?: MatchMode;
  category_id?: string;
}

interface RuleBuilderDialogProps {
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
  /** Modifica questa regola invece di crearne una nuova. */
  rule?: Rule | null;
  /** Movimento di partenza: le sue parole diventano i pulsanti della regola. */
  transaction?: Transaction | null;
  /** Condizioni e categoria di partenza (es. un'opzione di suggerimento). */
  defaults?: RuleBuilderDefaults;
}

const TEXT_OPERATORS = ["contains", "not_contains", "starts_with", "ends_with", "equals", "regex"] as const;
const MERCHANT_OPERATORS = [
  "merchant_equals",
  "contains",
  "not_contains",
  "starts_with",
  "ends_with",
  "equals",
  "regex",
] as const;

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function transactionText(transaction: Transaction): string {
  return transaction.description_normalized ?? transaction.description_raw;
}

export function RuleBuilderDialog({ open, onClose, onSaved, rule, transaction, defaults }: RuleBuilderDialogProps) {
  const { t } = useTranslation(["rules", "common", "enums"]);
  const { data: categories } = useCategories();
  const categoryLabel = useCategoryLabel();
  const createRule = useCreateRule();
  const updateRule = useUpdateRule();
  const reclassify = useTriggerReclassification();
  const isEditing = !!rule;

  // Il Dialog rimette il focus sul primo campo a ogni cambio di identita' di
  // `onClose`: al foglio passiamo sempre la stessa funzione.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const stableClose = useCallback(() => closeRef.current(), []);

  const tokens = useMemo(() => (transaction ? tokenizeDescription(transactionText(transaction)) : []), [transaction]);
  const stableIndexes = useMemo(() => stableTokenIndexes(tokens), [tokens]);

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [extra, setExtra] = useState<RuleCondition[]>([]);
  const [matchMode, setMatchMode] = useState<MatchMode>("all");
  const [categoryId, setCategoryId] = useState("");
  const [name, setName] = useState("");
  const [priority, setPriority] = useState("100");
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const [applyExisting, setApplyExisting] = useState(true);
  const [impactOpen, setImpactOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setFormError(null);
    setNotice(null);
    setSubmitted(false);
    setImpactOpen(false);
    setApplyExisting(true);
    if (rule) {
      setSelected(new Set());
      setExtra(rule.conditions);
      setMatchMode(rule.match_mode);
      setCategoryId(rule.category_id);
      setName(rule.name);
      setPriority(String(rule.priority));
      setCustomizeOpen(true);
      return;
    }
    const initialConditions = defaults?.conditions ?? [];
    setMatchMode(defaults?.match_mode ?? "all");
    setCategoryId(defaults?.category_id ?? transaction?.category_id ?? "");
    setName("");
    setPriority("100");
    if (transaction) {
      const fromDefaults = conditionsToSelection(tokens, initialConditions);
      const matchedAll = initialConditions.every(
        (c) => c.field === "description" && c.operator === "contains",
      );
      // Un suggerimento riconoscibile nelle parole del movimento le seleziona;
      // altrimenti si parte dall'ultima parte fissa (di solito la causale).
      setSelected(fromDefaults.size > 0 && matchedAll ? fromDefaults : defaultSelection(tokens));
      setExtra(matchedAll ? [] : initialConditions);
      setCustomizeOpen(false);
    } else {
      setSelected(new Set());
      setExtra(initialConditions.length > 0 ? initialConditions : [emptyTextCondition()]);
      setCustomizeOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo all'apertura
  }, [open]);

  const pickerConditions = useMemo(() => selectionToConditions(tokens, selected), [tokens, selected]);
  const conditions = useMemo<RuleCondition[]>(() => [...pickerConditions, ...extra], [pickerConditions, extra]);
  const invalid = hasInvalidCondition(conditions);
  const effectiveMode: MatchMode = conditions.length > 1 ? matchMode : "all";

  const impactInput = useMemo<RuleImpactInput | null>(() => {
    if (!open || invalid || !categoryId) return null;
    return { conditions: normalizeConditions(conditions), match_mode: effectiveMode, category_id: categoryId };
  }, [open, invalid, categoryId, conditions, effectiveMode]);
  const debouncedImpactInput = useDebounced(impactInput);
  const preview = useRulePreview(summaryInput(debouncedImpactInput));
  const settled = JSON.stringify(debouncedImpactInput) === JSON.stringify(impactInput);

  const toggleToken = (index: number) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const removePickerCondition = (index: number) => {
    const phrase = pickerConditions[index];
    if (!phrase) return;
    const words = conditionsToSelection(tokens, [phrase]);
    setSelected((current) => new Set([...current].filter((i) => !words.has(i))));
  };

  const updateExtra = (index: number, next: RuleCondition) =>
    setExtra((current) => current.map((condition, i) => (i === index ? next : condition)));
  const removeExtra = (index: number) => setExtra((current) => current.filter((_, i) => i !== index));
  const canAddMore = conditions.length < MAX_CONDITIONS;
  const addExtra = (condition: RuleCondition) => {
    setExtra((current) => [...current, condition]);
    setCustomizeOpen(true);
  };

  // Parola che distingue il movimento di partenza da quello in conflitto
  // (es. "CASHBACK"): si propone di escluderla, salvo che lo sia gia'.
  const excludeWord = useMemo(() => {
    const sample = preview.data?.conflict_samples?.[0];
    if (!sample || tokens.length === 0) return null;
    const word = exclusionWord(sample, tokens);
    const already = conditions.some(
      (c) => c.field !== "amount" && c.operator === "not_contains" && c.value.toLowerCase() === word?.toLowerCase(),
    );
    return word && !already ? word : null;
  }, [preview.data, tokens, conditions]);

  const excludeConflict = (word: string) => {
    // "Non contiene" ha senso solo in AND con la frase principale.
    setMatchMode("all");
    addExtra({ field: "description", operator: "not_contains", value: word });
  };

  const onSubmit = async () => {
    setSubmitted(true);
    setFormError(null);
    if (invalid || !categoryId) return;
    const payload = {
      name: name.trim() || autoRuleName(conditions),
      conditions: normalizeConditions(conditions),
      match_mode: effectiveMode,
      category_id: categoryId,
      priority: Number.parseInt(priority, 10) || 100,
    };
    setSaving(true);
    try {
      const saved = isEditing
        ? await updateRule.mutateAsync({ id: rule.id, ...payload })
        : await createRule.mutateAsync(payload);
      onSaved?.();
      const toApply = !isEditing && applyExisting && (preview.data?.would_change ?? 0) > 0;
      if (!toApply) {
        stableClose();
        return;
      }
      try {
        await reclassify.mutateAsync({ scope: "all_except_manual", run_ai: false, rule_id: saved.id });
        setNotice(t("rules:apply.started"));
      } catch (error) {
        setNotice(error instanceof ApiError && error.status === 409 ? t("rules:apply.busy") : t("rules:apply.failed"));
      }
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("rules:dialog.error")));
    } finally {
      setSaving(false);
    }
  };

  const errorText = (error: ConditionError | null): string | undefined => {
    if (!submitted || !error) return undefined;
    return {
      value: t("rules:validation.value"),
      regex: t("rules:validation.invalidRegex"),
      regexLength: t("rules:validation.regexLength"),
      bounds: t("rules:validation.bounds"),
      order: t("rules:validation.order"),
    }[error];
  };

  const targetLabel = categoryId ? categoryLabel(categories, categoryId) : "";
  const title = isEditing ? t("rules:dialog.editTitle") : t("rules:dialog.createTitle");
  const showPicker = tokens.length > 0;
  const previewData = !preview.isError && settled ? preview.data : undefined;

  const footer = notice ? (
    <Button onClick={stableClose}>{t("common:actions.close")}</Button>
  ) : (
    <>
      <Button type="button" variant="secondary" onClick={stableClose}>
        {t("common:actions.cancel")}
      </Button>
      <Button type="button" onClick={() => void onSubmit()} loading={saving}>
        {isEditing ? t("rules:dialog.submitEdit") : t("rules:dialog.submitCreate")}
      </Button>
    </>
  );

  return (
    <>
      <ResponsiveSheet open={open} onClose={stableClose} title={title} footer={footer} size="lg">
        {notice ? (
          <p role="status" className="text-sm text-text">
            {notice}
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            {showPicker && (
              <section aria-label={t("rules:picker.title")} className="flex flex-col gap-2">
                <p className="text-sm font-medium text-text">{t("rules:picker.title")}</p>
                <p className="text-xs text-text-muted">{t("rules:picker.hint")}</p>
                <div className="flex flex-wrap gap-2">
                  {tokens.map((token, index) =>
                    token.variable ? (
                      <span
                        key={index}
                        className="inline-flex min-h-11 items-center rounded-lg border border-dashed border-border px-3 text-sm text-text-muted md:min-h-9"
                      >
                        {token.text}
                      </span>
                    ) : (
                      <button
                        key={index}
                        type="button"
                        aria-pressed={selected.has(index)}
                        onClick={() => toggleToken(index)}
                        className={`inline-flex min-h-11 items-center rounded-lg border px-3 text-sm font-medium md:min-h-9 ${
                          selected.has(index)
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-border bg-surface text-text hover:bg-surface-hover"
                        }`}
                      >
                        {token.text}
                      </button>
                    ),
                  )}
                </div>
                {tokens.some((token) => token.variable) && (
                  <p className="text-xs text-text-muted">{t("rules:picker.variableHint")}</p>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setSelected(new Set(stableIndexes))}>
                    {t("rules:picker.selectStable")}
                  </Button>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
                    {t("rules:picker.clear")}
                  </Button>
                </div>
              </section>
            )}

            <div className="rounded-lg bg-surface-hover px-3 py-2">
              <RuleSentence conditions={conditions} matchMode={effectiveMode} categoryName={targetLabel || undefined} />
            </div>

            <CategoryPicker
              error={submitted && !categoryId ? t("rules:validation.category") : undefined}
              value={categoryId}
              onChange={(event) => setCategoryId(event.target.value)}
            />

            <section aria-label={t("rules:impact.title")} className="flex flex-col gap-2">
              {!categoryId || invalid ? (
                <p className="text-sm text-text-muted">
                  {!categoryId ? t("rules:impact.needCategory") : t("rules:sentence.empty")}
                </p>
              ) : preview.isError ? (
                <p role="alert" className="text-sm text-danger">
                  {t("rules:impact.error")}
                </p>
              ) : !previewData ? (
                <>
                  <p className="text-xs text-text-muted">{t("rules:impact.loading")}</p>
                  <RuleImpactSkeleton />
                </>
              ) : (
                <>
                  <RuleImpactCounters preview={previewData} />
                  <RuleImpactWarning preview={previewData} excludeWord={excludeWord} onExclude={excludeConflict} />
                  {previewData.total === 0 ? (
                    <p className="text-sm text-text-muted">{t("rules:impact.none")}</p>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setImpactOpen(true)}
                      className="inline-flex min-h-11 items-center justify-between rounded-lg text-sm font-medium text-primary"
                    >
                      {t("rules:impact.see", { count: previewData.total })}
                      <span aria-hidden="true">›</span>
                    </button>
                  )}
                </>
              )}
            </section>

            <section className="flex flex-col gap-3">
              <button
                type="button"
                aria-expanded={customizeOpen}
                onClick={() => setCustomizeOpen((value) => !value)}
                className="inline-flex min-h-11 items-center gap-2 self-start text-sm font-medium text-text"
              >
                <Wand2 className="h-4 w-4 text-text-muted" aria-hidden="true" />
                {customizeOpen ? t("rules:customize.close") : t("rules:customize.open")}
              </button>

              {customizeOpen && (
                <div className="flex flex-col gap-3">
                  {conditions.length > 1 && (
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="text-text-muted">{t("rules:customize.matchMode")}</span>
                      <div className="grid grid-cols-2 overflow-hidden rounded-lg border border-border" role="group">
                        {(["all", "any"] as const).map((mode) => (
                          <button
                            key={mode}
                            type="button"
                            aria-pressed={matchMode === mode}
                            onClick={() => setMatchMode(mode)}
                            className={`min-h-11 px-4 md:min-h-9 ${
                              matchMode === mode ? "bg-primary/10 font-semibold text-primary" : "bg-surface"
                            }`}
                          >
                            {t(`rules:customize.${mode}`)}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {pickerConditions.map((condition, index) => (
                    <ConditionCard key={`p-${index}`} onRemove={() => removePickerCondition(index)}>
                      <RuleSentence conditions={[condition]} matchMode="all" className="!text-sm" />
                    </ConditionCard>
                  ))}

                  {extra.map((condition, index) => (
                    <ConditionCard key={`e-${index}`} onRemove={() => removeExtra(index)}>
                      <ConditionEditor
                        condition={condition}
                        error={errorText(validateCondition(condition))}
                        onChange={(next) => updateExtra(index, next)}
                      />
                    </ConditionCard>
                  ))}

                  {canAddMore && (
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" variant="secondary" size="sm" onClick={() => addExtra(emptyTextCondition())}>
                        <Plus className="h-4 w-4" aria-hidden="true" /> {t("rules:customize.addText")}
                      </Button>
                      {!conditions.some((c) => c.field === "amount") && (
                        <Button type="button" variant="secondary" size="sm" onClick={() => addExtra(emptyAmountCondition())}>
                          <Plus className="h-4 w-4" aria-hidden="true" /> {t("rules:customize.addAmount")}
                        </Button>
                      )}
                    </div>
                  )}

                  <details className="text-sm">
                    <summary className="flex min-h-11 cursor-pointer items-center text-text-muted">
                      {t("rules:customize.advanced")}
                    </summary>
                    <div className="mt-2 grid gap-3 sm:grid-cols-2">
                      <Input
                        label={t("rules:fields.name")}
                        hint={t("rules:customize.nameHint")}
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        maxLength={100}
                      />
                      <Input
                        label={t("rules:fields.priority")}
                        hint={t("rules:priorityHint")}
                        type="number"
                        value={priority}
                        onChange={(event) => setPriority(event.target.value)}
                      />
                    </div>
                  </details>
                </div>
              )}
              {submitted && conditions.length === 0 && (
                <p role="alert" className="text-sm text-danger">
                  {t("rules:validation.conditions")}
                </p>
              )}
            </section>

            {!isEditing && previewData && previewData.would_change > 0 && (
              <label className="flex min-h-11 items-start gap-3 text-sm text-text">
                <input
                  type="checkbox"
                  checked={applyExisting}
                  onChange={(event) => setApplyExisting(event.target.checked)}
                  className="mt-0.5 h-5 w-5 shrink-0"
                />
                <span>
                  {t("rules:apply.label", { count: previewData.would_change })}
                  <span className="block text-xs text-text-muted">{t("rules:apply.hint")}</span>
                </span>
              </label>
            )}

            {formError && (
              <p role="alert" className="text-sm text-danger">
                {formError}
              </p>
            )}
          </div>
        )}
      </ResponsiveSheet>

      {impactInput && (
        <RuleImpactSheet
          open={impactOpen}
          onClose={() => setImpactOpen(false)}
          input={impactInput}
          sentence={<RuleSentence conditions={conditions} matchMode={effectiveMode} categoryName={targetLabel} />}
          targetLabel={targetLabel}
        />
      )}
    </>
  );
}

function ConditionCard({ children, onRemove }: { children: React.ReactNode; onRemove: () => void }) {
  const { t } = useTranslation("rules");
  return (
    <div className="flex items-start justify-between gap-2 rounded-lg border border-border p-3">
      <div className="min-w-0 flex-1">{children}</div>
      <button
        type="button"
        onClick={onRemove}
        aria-label={t("customize.remove")}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover hover:text-text md:h-9 md:w-9"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}

function ConditionEditor({
  condition,
  error,
  onChange,
}: {
  condition: RuleCondition;
  error?: string;
  onChange: (next: RuleCondition) => void;
}) {
  const { t } = useTranslation(["rules", "enums"]);
  if (condition.field === "amount") {
    const amount: AmountCondition = condition;
    return (
      <div className="flex flex-col gap-2">
        <FieldSelect value="amount" onChange={(field) => onChange(switchField(condition, field))} />
        <div className="grid grid-cols-2 gap-2">
          <Input
            label={t("rules:customize.min")}
            inputMode="decimal"
            value={amount.min ?? ""}
            onChange={(event) => onChange({ ...amount, min: event.target.value })}
            error={error}
          />
          <Input
            label={t("rules:customize.max")}
            inputMode="decimal"
            value={amount.max ?? ""}
            onChange={(event) => onChange({ ...amount, max: event.target.value })}
          />
        </div>
        <p className="text-xs text-text-muted">{t("rules:customize.amountHint")}</p>
      </div>
    );
  }
  const text: TextCondition = condition;
  const operators = text.field === "merchant" ? MERCHANT_OPERATORS : TEXT_OPERATORS;
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2">
        <FieldSelect value={text.field} onChange={(field) => onChange(switchField(condition, field))} />
        <Select
          label={t("rules:customize.operator")}
          value={text.operator}
          onChange={(event) => onChange({ ...text, operator: event.target.value as TextCondition["operator"] })}
        >
          {operators.map((operator) => (
            <option key={operator} value={operator}>
              {t(`enums:ruleOperator.${operator}`)}
            </option>
          ))}
        </Select>
      </div>
      <Input
        label={t("rules:customize.value")}
        value={text.value}
        onChange={(event) => onChange({ ...text, value: event.target.value })}
        error={error}
      />
      {text.operator === "regex" && <p className="text-xs text-text-muted">{t("rules:customize.regexHint")}</p>}
    </div>
  );
}

function FieldSelect({
  value,
  onChange,
}: {
  value: "description" | "merchant" | "amount";
  onChange: (field: "description" | "merchant" | "amount") => void;
}) {
  const { t } = useTranslation("rules");
  return (
    <Select
      label={t("customize.field")}
      value={value}
      onChange={(event) => onChange(event.target.value as "description" | "merchant" | "amount")}
    >
      {(["description", "merchant", "amount"] as const).map((field) => (
        <option key={field} value={field}>
          {t(`customize.fields.${field}`)}
        </option>
      ))}
    </Select>
  );
}

function switchField(condition: RuleCondition, field: "description" | "merchant" | "amount"): RuleCondition {
  if (field === "amount") return emptyAmountCondition();
  const value = condition.field === "amount" ? "" : condition.value;
  return {
    field,
    operator: field === "merchant" ? "merchant_equals" : "contains",
    value,
  };
}
