export type IndexSnapshot = {
  name: string;
  code: string;
  close: number;
  pct_change: number;
};

export type NewsItem = {
  title: string;
  url: string;
  source: string | null;
  summary: string;
  published_at: string | null;
  matched_sector: string | null;
  weight: number;
};

export type ReportNarrative = {
  conclusion: string;
  overview: string;
  sector_commentary: string[];
  watchlist: string[];
  tomorrow: string;
  risks: string[];
};

export type StockCandidate = {
  code: string;
  name: string;
  pct_change: number;
  turnover_cny: number | null;
  tags: string[];
};

export type SectorCandidate = {
  name: string;
  score: number;
  rank: number;
  pct_change: number;
  reason: string;
  top_stocks: StockCandidate[];
  news_summaries: string[];
  factor_scores: Record<string, number>;
  confidence: string;
};

export type PredictionReview = {
  previous_prediction: string;
  actual_result: string;
  correct_items: string[];
  missed_items: string[];
  revision: string;
  source: "manual_placeholder" | "previous_report";
};

export type TomorrowJudgement = {
  most_likely_to_continue: string;
  most_likely_to_diverge: string;
  rotation_candidates: string[];
  defensive_candidates: string[];
  core_view: string;
};

export type MarketOverviewTable = {
  index_rows: Array<Record<string, string>>;
  emotion_rows: Array<Record<string, string>>;
  structure_features: string[];
  capital_flow_summary: string;
};

export type StructuredSectorReview = {
  sector: string;
  headline: string;
  stage: string;
  strengths: string[];
  weaknesses: string[];
  logic: string;
  sustainability: "high" | "medium" | "low";
  next_day_view: string;
  watch_items: string[];
  avoid_items: string[];
};

export type SustainabilityRank = {
  rank: number;
  sector: string;
  rating: "high" | "medium" | "low";
  reason: string;
};

export type ActionDiscipline = {
  focus: string[];
  avoid: string[];
  final_view: string;
};

export type StructuredReviewDTO = {
  topic: string;
  prediction_review: PredictionReview;
  tomorrow_judgement: TomorrowJudgement;
  market_overview: MarketOverviewTable;
  sector_reviews: StructuredSectorReview[];
  sustainability_ranking: SustainabilityRank[];
  action_discipline: ActionDiscipline;
};

export type WatchlistItem = {
  symbol: string;
  code: string;
  exchange: "SH" | "SZ" | "BJ";
  name: string | null;
  source: string;
};

export type WatchlistImportResult = {
  import_id: number | null;
  item_count: number;
  items: WatchlistItem[];
  warnings: string[];
};

export type OcrProviderStatus = {
  provider: string;
  status: "success" | "fallback";
  fallback_used: boolean;
  reason: string | null;
};

export type WatchlistOcrPreviewResult = {
  preview_id: string;
  source_name: string;
  item_count: number;
  items: WatchlistItem[];
  warnings: string[];
  ocr_text: string;
  provider_status: OcrProviderStatus;
  image_snapshot_path: string;
  ocr_text_snapshot_path: string;
  preview_snapshot_path: string;
};

export type WatchlistMatch = {
  symbol: string;
  name: string | null;
  sector: string | null;
  pct_change: number | null;
  reason: string;
};

export type WatchlistObservation = {
  import_id: number | null;
  total_count: number;
  quote_count: number;
  strongest: WatchlistMatch[];
  weakest: WatchlistMatch[];
  sector_matches: WatchlistMatch[];
  notes: string[];
};

export type ReportKind = "close" | "midday" | "weekly";

export type QualityGateIssue = {
  code: string;
  severity: string;
  message: string;
  details: Record<string, unknown>;
};

export type PublishStatus = "publishable" | "degraded" | "blocked" | "not_applicable" | "not_scored";

export type QualityGateResult = {
  score: number | null;
  publish_status: PublishStatus;
  label: string;
  summary: string;
  hard_failures: QualityGateIssue[];
  warnings: QualityGateIssue[];
  provider_summary: Record<string, unknown>;
};

export type ReportDTO = {
  trade_date: string;
  kind: ReportKind;
  title: string;
  indices: IndexSnapshot[];
  breadth: {
    up_count: number;
    down_count: number;
    limit_up_count: number;
    limit_down_count: number;
  };
  turnover_cny: number;
  market_state_tags: string[];
  sectors: SectorCandidate[];
  narrative: ReportNarrative;
  news: NewsItem[];
  structured_review?: StructuredReviewDTO | null;
  watchlist_observation?: WatchlistObservation | null;
  quality_gate?: QualityGateResult | null;
  algorithm_versions: Record<string, string>;
};

export type ProviderStatus = {
  provider: string;
  status: "success" | "fallback" | "disabled" | "failed";
  fallback_used: boolean;
  reason: string | null;
};

export type SectorProviderStatus = ProviderStatus & {
  sector: string;
};

export type ProviderStatusSummary = {
  market: ProviderStatus;
  market_quote?: ProviderStatus;
  news: SectorProviderStatus[];
  quote?: ProviderStatus;
  watchlist_quote?: ProviderStatus;
  review_sources?: Array<ProviderStatus & { source?: string }>;
};

export type CreateReportResponse = {
  report: ReportDTO;
  validation: {
    is_valid: boolean;
    errors: string[];
  };
  assets: {
    root: string;
    version: string;
    html: string;
    png: string;
    pdf?: string | null;
    named_html?: string;
    named_png?: string;
    named_pdf?: string;
    html_url?: string;
    png_url?: string;
    pdf_url?: string | null;
  };
  provider_status: ProviderStatusSummary;
};

export type ReportListItem = {
  id: number;
  trade_date: string;
  kind: ReportKind;
  kind_label: string;
  version: string;
  status: string;
  asset_dir: string;
  html: string;
  png: string;
  pdf: string | null;
  html_url: string;
  png_url: string;
  pdf_url: string | null;
  created_at: string | null;
  quality_score: number | null;
  publish_status: PublishStatus | null;
  quality_summary: string | null;
  quality_gate?: QualityGateResult | null;
};

export type ReportListResponse = {
  items: ReportListItem[];
};

export type DeleteReportResponse = {
  deleted: boolean;
  id: number;
};

export type ConfigStatusState = "ready" | "missing_key" | "disabled" | "local" | "experimental";

export type ConfigStatusItem = {
  name: string;
  role: string;
  configured: boolean;
  enabled: boolean;
  status: ConfigStatusState;
  detail: string;
};

export type ConfigStatusResponse = {
  items: ConfigStatusItem[];
};

export type ReportScheduleLastResult = {
  status: string;
  trade_date: string;
  kind: ReportKind;
  reason?: string;
  publish_status?: PublishStatus;
  quality_score?: number | null;
  quality_summary?: string | null;
};

export type ReportScheduleStatus = {
  enabled: boolean;
  kind: "close";
  time: string;
  timezone: string;
  next_run_at: string | null;
  last_run_at: string | null;
  last_result: ReportScheduleLastResult | null;
};

export type ReportScheduleUpdate = {
  enabled: boolean;
  time: string;
  timezone: string;
};

export type WatchlistAlertEvent = {
  id: number;
  stock_id: number | null;
  symbol: string;
  name: string | null;
  event_type: "risk" | "opportunity" | "plan" | "intraday" | "stale_review";
  severity: "high" | "medium" | "low";
  status: "active" | "sent" | "acknowledged" | "muted" | "resolved";
  trigger_reason: string;
  ai_comment: string | null;
  source_status: Record<string, unknown>;
  market_snapshot: Record<string, unknown>;
  rule_snapshot: Record<string, unknown>;
  notification_status: Record<string, unknown>;
  first_seen_at: string;
  last_seen_at: string;
  muted_until?: string | null;
};

export type WatchlistAlertListResponse = {
  items: WatchlistAlertEvent[];
};

export type WatchlistAlertScheduleStatus = {
  enabled: boolean;
  morning_time: string;
  afternoon_time: string;
  review_time: string;
  timezone: string;
  last_run_at: string | null;
  last_result: Record<string, unknown> | null;
};

export type TickFlowHealthStatus = {
  configured: boolean;
  status: string;
  base_url?: string;
  timeout_seconds?: number;
  realtime_quotes: string;
  daily_kline: string;
  minute_kline: string;
  latency_ms: number | null;
  last_error: string | null;
  fallback_source: string | null;
};

export type WatchlistPoolGroup = {
  id: number;
  name: string;
  is_default: boolean;
  sort_order: number;
};

export type WatchlistPoolStock = {
  id: number;
  symbol: string;
  code: string;
  exchange: string;
  name: string | null;
  status: "观察中" | "持有中";
  tags: string[];
  entry_reason: string | null;
  planned_buy_price: string | null;
  invalid_condition: string | null;
  themes: string[];
  last_review_conclusion: string | null;
  today_risk_hint: string | null;
  groups: WatchlistPoolGroup[];
};

export type WatchlistPoolState = {
  groups: WatchlistPoolGroup[];
  stocks: WatchlistPoolStock[];
};

export type WatchlistStockPayload = {
  symbol?: string;
  code?: string | null;
  exchange?: string | null;
  name?: string | null;
  group_ids?: number[];
  tags?: string[];
  status?: "观察中" | "持有中";
  entry_reason?: string | null;
  planned_buy_price?: string | null;
  invalid_condition?: string | null;
  themes?: string[];
  last_review_conclusion?: string | null;
  today_risk_hint?: string | null;
};

export type DataSourceSelectionMode = "single" | "multiple";

export type DataSourceOptionItem = {
  key: string;
  label: string;
  role: string;
  configured: boolean;
  enabled: boolean;
  status: ConfigStatusState;
  requires_key: boolean;
  experimental: boolean;
  detail: string;
};

export type DataSourceOptionCategory = {
  key: "market_provider" | "news_provider" | "review_sources";
  label: string;
  selection: DataSourceSelectionMode;
  options: DataSourceOptionItem[];
};

export type DataSourceOptionsCurrent = {
  market_provider: string;
  news_provider: string;
  review_sources: string[];
  fallback_enabled: boolean;
  updated_at: string | null;
};

export type DataSourceOptionsResponse = {
  current: DataSourceOptionsCurrent;
  categories: DataSourceOptionCategory[];
};

export type DataSourceOptionsUpdate = {
  market_provider: string;
  news_provider: string;
  review_sources: string[];
  fallback_enabled: boolean;
};
