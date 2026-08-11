// Tipi condivisi, scritti a mano a partire dagli schemi Pydantic del
// backend (SPEC_FE §126: "il frontend deve consumare dati tipizzati" —
// niente generazione automatica dall'OpenAPI in questa slice, i tipi
// rilevanti sono pochi e stabili).

export type Uuid = string;
export type IsoDate = string;
export type IsoDateTime = string;

export interface User {
  id: Uuid;
  email: string;
  display_name: string;
  created_at: IsoDateTime;
}

export interface Me extends User {
  workspace_id: Uuid;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: Me;
}

export const ACCOUNT_TYPES = ["checking", "savings", "brokerage", "cash", "credit_card", "other"] as const;
export type AccountType = (typeof ACCOUNT_TYPES)[number];

export interface FinancialAccount {
  id: Uuid;
  workspace_id: Uuid;
  bank_id: Uuid | null;
  name: string;
  account_type: AccountType;
  currency: string;
  account_identifier_masked: string | null;
  is_active: boolean;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface Category {
  id: Uuid;
  workspace_id: Uuid | null;
  parent_id: Uuid | null;
  name: string;
  code: string;
  is_system: boolean;
  is_active: boolean;
  sort_order: number;
}

export const TRANSACTION_TYPES = [
  "expense",
  "income",
  "transfer",
  "investment",
  "dividend",
  "interest",
  "fee",
  "tax",
  "refund",
  "adjustment",
] as const;
export type TransactionType = (typeof TRANSACTION_TYPES)[number];

export interface Transaction {
  id: Uuid;
  workspace_id: Uuid;
  financial_account_id: Uuid;
  import_id: Uuid | null;
  category_id: Uuid | null;
  transaction_date: IsoDate;
  value_date: IsoDate | null;
  description_raw: string;
  description_normalized: string | null;
  merchant: string | null;
  reference: string | null;
  amount: string; // Decimal serializzato come stringa da Pydantic
  currency: string;
  direction: "debit" | "credit";
  transaction_type: TransactionType;
  balance_after: string | null;
  status: "pending" | "confirmed";
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export const CLASSIFICATION_METHODS = ["rule", "ai", "user", "manual", "system"] as const;
export type ClassificationMethod = (typeof CLASSIFICATION_METHODS)[number];

export interface Classification {
  id: Uuid;
  transaction_id: Uuid;
  method: ClassificationMethod;
  provider: string | null;
  model: string | null;
  category_id: Uuid | null;
  score: string | null;
  explanation: string | null;
  created_by_user_id: Uuid | null;
  created_at: IsoDateTime;
}

export const RULE_FIELDS = ["description", "merchant"] as const;
export type RuleField = (typeof RULE_FIELDS)[number];

export const RULE_OPERATORS = [
  "equals",
  "contains",
  "starts_with",
  "ends_with",
  "regex",
  "merchant_equals",
] as const;
export type RuleOperator = (typeof RULE_OPERATORS)[number];

export interface Rule {
  id: Uuid;
  workspace_id: Uuid;
  name: string;
  field: RuleField;
  operator: RuleOperator;
  value: string;
  category_id: Uuid;
  priority: number;
  is_active: boolean;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface RuleSuggestion {
  match_field: RuleField;
  match_value: string;
  category_id: Uuid;
  occurrences: number;
  transaction_ids: Uuid[];
}

export const AI_PROVIDERS = ["ollama", "openai", "anthropic", "custom"] as const;
export type AIProvider = (typeof AI_PROVIDERS)[number];

/** Un profilo salvato (SPEC §25-28) — un workspace puo' averne piu' d'uno,
 * anche dello stesso provider, ma al massimo UNO con `is_active: true`. */
export interface AIProfile {
  id: Uuid;
  name: string;
  provider: AIProvider;
  endpoint: string | null;
  model: string | null;
  api_key_set: boolean;
  is_active: boolean;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface AIProfileCreate {
  name: string;
  provider: AIProvider;
  endpoint?: string | null;
  model?: string | null;
  api_key?: string;
}

export interface AIProfileUpdate {
  /** `provider` non e' modificabile: cambiarlo richiede un nuovo profilo. */
  name?: string;
  endpoint?: string | null;
  model?: string | null;
  /** undefined = mantieni la chiave salvata, "" = rimuovila, altro = sostituiscila. */
  api_key?: string;
}

/** Payload di test/elenco-modelli per un profilo NON ANCORA salvato. */
export interface AIConnectionCheckRequest {
  provider: AIProvider;
  endpoint?: string | null;
  model?: string | null;
  api_key?: string;
}

export interface AITestConnectionResult {
  success: boolean;
  message: string;
}

export interface AIModelListResult {
  success: boolean;
  models: string[];
  message: string;
}

export type ImportFileType = "csv" | "pdf";
export type ImportStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "parsing"
  | "completed"
  | "failed"
  | "cancelled";

export interface MappingColumns {
  transaction_date: string;
  value_date: string | null;
  description_raw: string;
  amount: string | null;
  amount_debit: string | null;
  amount_credit: string | null;
  direction: string | null;
  currency: string | null;
  reference: string | null;
  balance_after: string | null;
}

export interface MappingConfig {
  delimiter: string;
  encoding: string;
  decimal_separator: string;
  thousands_separator: string | null;
  date_format: string;
  skip_rows: number;
  default_currency: string;
  amount_mode: "single_signed" | "single_absolute_with_direction" | "separate_debit_credit";
  debit_markers: string[];
  columns: MappingColumns;
}

export interface ImportMapping {
  id: Uuid;
  workspace_id: Uuid;
  financial_account_id: Uuid | null;
  name: string;
  config: MappingConfig;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface ImportRecord {
  id: Uuid;
  workspace_id: Uuid;
  financial_account_id: Uuid;
  import_mapping_id: Uuid | null;
  mapping_config: MappingConfig | null;
  file_type: ImportFileType;
  bank_id: Uuid | null;
  bank_parser_id: Uuid | null;
  job_id: string | null;
  status: ImportStatus;
  filename: string;
  file_hash: string;
  file_size: number;
  period_start: IsoDate | null;
  period_end: IsoDate | null;
  transactions_found: number;
  transactions_imported: number;
  error_message: string | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
  completed_at: IsoDateTime | null;
}

export interface ImportPreview {
  columns: string[];
  sample_rows: string[][];
  suggested_mapping: MappingConfig | null;
  available_mappings: ImportMapping[];
  detected_bank_code: string | null;
  detected_bank_name: string | null;
}

export interface ImportUploadResponse {
  import: ImportRecord;
  preview: ImportPreview;
}

export interface JobEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface ApiErrorBody {
  detail: string | { detail: string; existing_import_id?: Uuid; existing_status?: string } | unknown;
}

// Analytics (milestone 08) — Decimal serializzati come stringa da Pydantic,
// stesso motivo di `Transaction.amount` sopra.

export const ANALYTICS_GRANULARITIES = ["day", "week", "month", "quarter", "year"] as const;
export type AnalyticsGranularity = (typeof ANALYTICS_GRANULARITIES)[number];

export type AnalyticsDirection = "expense" | "income";

export interface AnalyticsPeriod {
  date_from: IsoDate;
  date_to: IsoDate;
}

export interface AnalyticsSummary {
  currency: string;
  period: AnalyticsPeriod;
  comparison_period: AnalyticsPeriod;
  liquidity: string;
  debt: string;
  investments: string;
  has_investments: boolean;
  income: string;
  expenses: string;
  net_cash_flow: string;
  previous_income: string;
  previous_expenses: string;
  previous_net_cash_flow: string;
}

export interface AccountBalance {
  financial_account_id: Uuid;
  name: string;
  account_type: AccountType;
  balance: string;
}

export interface AnalyticsBalances {
  currency: string;
  as_of: IsoDate;
  accounts: AccountBalance[];
  liquidity_total: string;
  debt_total: string;
  investment_total: string;
  has_investments: boolean;
}

export interface BalanceHistoryPoint {
  period: IsoDate;
  balance: string;
}

export interface AnalyticsBalanceHistory {
  currency: string;
  granularity: AnalyticsGranularity;
  period: AnalyticsPeriod;
  points: BalanceHistoryPoint[];
}

export interface CashFlowPoint {
  period: IsoDate;
  income: string;
  expenses: string;
  net: string;
}

export interface AnalyticsCashFlow {
  currency: string;
  granularity: AnalyticsGranularity;
  period: AnalyticsPeriod;
  points: CashFlowPoint[];
}

export interface CategoryBreakdownItem {
  category_id: Uuid | null;
  name: string;
  total: string;
  share: string;
  transactions_count: number;
}

export interface AnalyticsCategoryBreakdown {
  currency: string;
  direction: AnalyticsDirection;
  period: AnalyticsPeriod;
  items: CategoryBreakdownItem[];
}

export interface MerchantBreakdownItem {
  merchant: string;
  total: string;
  share: string;
  transactions_count: number;
}

export interface AnalyticsMerchantBreakdown {
  currency: string;
  direction: AnalyticsDirection;
  period: AnalyticsPeriod;
  items: MerchantBreakdownItem[];
}
