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
