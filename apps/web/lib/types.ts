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

export type ReportDTO = {
  trade_date: string;
  kind: "close";
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
  news: SectorProviderStatus[];
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
  };
  provider_status: ProviderStatusSummary;
};
