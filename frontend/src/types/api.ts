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
  /** Milestone 10: se false, nessuna superficie Google in nessuna
   * direzione (nav, pagina, endpoint) — l'istanza gira con
   * GOOGLE_ENABLED=false, stato di default. */
  google_enabled: boolean;
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
  iban: string | null;
  is_active: boolean;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

/** Milestone 09.5c: IBAN precedenti di un conto (un istituto puo' cambiare
 * l'IBAN pur restando lo stesso conto) — vedi transfer_recognition.py. */
export interface IbanHistoryEntry {
  id: Uuid;
  iban: string;
  created_at: IsoDateTime;
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

export const ANALYTICS_GRANULARITIES = ["day", "week", "month", "quarter", "semester", "year"] as const;
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

// Portfolio (milestone 09a) — nessun market data ancora: tutti i valori
// monetari legati a un asset sono "a costo" (average_cost), non a mercato.

export const ASSET_TYPES = ["etf", "stock", "bond", "crypto", "fund", "cash", "other"] as const;
export type AssetType = (typeof ASSET_TYPES)[number];

export interface Asset {
  id: Uuid;
  workspace_id: Uuid;
  symbol: string | null;
  isin: string | null;
  name: string;
  asset_type: AssetType;
  currency: string;
  notes: string | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface Portfolio {
  id: Uuid;
  workspace_id: Uuid;
  name: string;
  description: string | null;
  currency: string;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface PortfolioAccountLink {
  id: Uuid;
  portfolio_id: Uuid;
  financial_account_id: Uuid;
  created_at: IsoDateTime;
}

export const INVESTMENT_TRANSACTION_TYPES = [
  "buy",
  "sell",
  "dividend",
  "deposit",
  "withdrawal",
  "fee",
  "tax",
  "split",
  "opening",
  "adjustment",
] as const;
export type InvestmentTransactionType = (typeof INVESTMENT_TRANSACTION_TYPES)[number];

export interface InvestmentTransaction {
  id: Uuid;
  workspace_id: Uuid;
  financial_account_id: Uuid;
  asset_id: Uuid | null;
  transaction_id: Uuid | null;
  trade_date: IsoDate;
  type: InvestmentTransactionType;
  quantity: string | null;
  price: string | null;
  amount: string;
  fees: string;
  tax: string;
  currency: string;
  source_type_raw: string | null;
  notes: string | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export const MARKET_DATA_PROVIDERS = ["manual", "stooq", "yahoo", "custom"] as const;
export type MarketDataProviderName = (typeof MARKET_DATA_PROVIDERS)[number];

/** Un profilo salvato (SPEC §38) — stesso pattern di `AIProfile`: piu' per
 * workspace, al massimo UNO con `is_active: true`. */
export interface MarketDataProfile {
  id: Uuid;
  name: string;
  provider: MarketDataProviderName;
  endpoint: string | null;
  api_key_set: boolean;
  price_field: string | null;
  currency_field: string | null;
  is_active: boolean;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface MarketDataProfileCreate {
  name: string;
  provider: MarketDataProviderName;
  endpoint?: string | null;
  api_key?: string;
  price_field?: string | null;
  currency_field?: string | null;
}

export interface MarketDataProfileUpdate {
  name?: string;
  endpoint?: string | null;
  api_key?: string;
  price_field?: string | null;
  currency_field?: string | null;
}

export interface MarketDataConnectionCheckRequest {
  provider: MarketDataProviderName;
  endpoint?: string | null;
  api_key?: string;
  price_field?: string | null;
  currency_field?: string | null;
}

export interface MarketDataTestConnectionResult {
  success: boolean;
  message: string;
}

export interface MarketDataRefreshTriggered {
  job_id: string;
}

export interface AssetPrice {
  id: Uuid;
  asset_id: Uuid;
  price_date: IsoDate;
  price: string;
  currency: string;
  source: MarketDataProviderName;
  created_at: IsoDateTime;
}

export interface PortfolioValuation {
  currency: string;
  as_of: IsoDate;
  market_value: string;
  cost_basis: string;
  unrealized_pl: string;
  realized_pl: string;
  has_market_data: boolean;
  has_holdings: boolean;
}

export interface AllocationItem {
  key: string;
  label: string;
  value: string;
  share: string;
}

export interface PortfolioAllocation {
  currency: string;
  as_of: IsoDate;
  has_market_data: boolean;
  by_asset_type: AllocationItem[];
  by_asset: AllocationItem[];
  by_account: AllocationItem[];
}

export interface PortfolioSnapshotPoint {
  snapshot_date: IsoDate;
  market_value: string;
  cost_basis: string;
  unrealized_pl: string;
  realized_pl: string;
  has_market_data: boolean;
}

export interface PortfolioPerformance {
  currency: string;
  points: PortfolioSnapshotPoint[];
}

export interface NetWorthSnapshotPoint {
  snapshot_date: IsoDate;
  liquidity: string;
  debt: string;
  investments: string;
  net_worth: string;
}

export interface NetWorthHistory {
  currency: string;
  points: NetWorthSnapshotPoint[];
}

export interface SnapshotRebuildTriggered {
  job_id: string;
}

/** Stato persistente dell'ultima esecuzione di un job async innescabile
 * manualmente (refresh prezzi, ricalcolo snapshot) — sopravvive a un
 * refresh pagina, a differenza del toast mostrato subito dopo il click.
 * `null` (nessun JobRun) significa "non ancora eseguito", non un errore. */
export interface JobRun {
  status: "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  message: string | null;
}

/** Milestone 09.5: mappatura tipi transazione configurabile per parser
 * (`app/services/transaction_type_mapping_service.py`). */
export interface TransactionTypeCount {
  transaction_type: TransactionType;
  count: number;
}

export interface TransactionTypeLabel {
  source_type_raw: string;
  total_count: number;
  // Puo' avere piu' di una riga: il default del parser per la stessa
  // etichetta puo' variare per direzione (es. "Transazione con carta").
  current_types: TransactionTypeCount[];
  override: TransactionType | null;
}

export interface TransactionTypeMappingUpsertResult {
  source_type_raw: string;
  transaction_type: TransactionType;
  reapply: { updated: number; skipped: number };
}

// Google Sheets export (milestone 10) — integrazione opzionale e isolata
// (SPEC §47/48/50/51/54): un'unica connessione per workspace, mai una
// lista di profili come AIProfile/MarketDataProfile.

export interface GoogleIntegration {
  google_account_email: string;
  spreadsheet_url: string;
  /** null = il file vive nella root "Il mio Drive" (nessuna cartella scelta via Picker). */
  drive_folder_name: string | null;
  connected_at: IsoDateTime;
  last_exported_at: IsoDateTime | null;
}

export interface ConnectUrlOut {
  authorize_url: string;
}

/** Access token a vita breve per il widget Google Picker — mai il
 * refresh_token, unica eccezione deliberata alla regola "mai token
 * dall'API" (vedi backend GoogleIntegrationOut/PickerTokenOut). */
export interface PickerToken {
  access_token: string;
  expires_in_seconds: number;
}

export interface SetDriveFolderRequest {
  folder_id: string | null;
  folder_name: string | null;
}

export interface GoogleExportRequest {
  date_from: IsoDate;
  date_to: IsoDate;
  include_portfolio?: boolean | null;
  include_charts?: boolean;
}

export interface GoogleExportTriggered {
  job_id: string;
}

export interface Position {
  id: Uuid;
  workspace_id: Uuid;
  financial_account_id: Uuid;
  asset_id: Uuid;
  quantity: string;
  average_cost: string;
  realized_pl: string;
  currency: string;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}
