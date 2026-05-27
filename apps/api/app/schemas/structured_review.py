from typing import Literal

from pydantic import BaseModel, Field


PredictionSource = Literal["manual_placeholder", "previous_report"]
SustainabilityRating = Literal["high", "medium", "low"]


class PredictionReview(BaseModel):
    previous_prediction: str
    actual_result: str
    correct_items: list[str] = Field(default_factory=list)
    missed_items: list[str] = Field(default_factory=list)
    bias_reasons: list[str] = Field(default_factory=list)
    revision: str
    source: PredictionSource = "manual_placeholder"


class TomorrowJudgement(BaseModel):
    most_likely_to_continue: str
    most_likely_to_diverge: str
    rotation_candidates: list[str] = Field(default_factory=list)
    defensive_candidates: list[str] = Field(default_factory=list)
    core_view: str
    operating_focus: list[str] = Field(default_factory=list)


class MarketOverviewTable(BaseModel):
    index_rows: list[dict[str, str]] = Field(default_factory=list)
    emotion_rows: list[dict[str, str]] = Field(default_factory=list)
    structure_features: list[str] = Field(default_factory=list)
    structure_notes: list[str] = Field(default_factory=list)
    capital_flow_summary: str


class AfterHoursNewsSummary(BaseModel):
    us_market_mapping: list[str] = Field(default_factory=list)
    us_market_conclusion: str = ""
    domestic_catalysts: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class CapitalRotationPath(BaseModel):
    actual_path: list[str] = Field(default_factory=list)
    path_summary: str = ""
    key_finding: str
    next_path_watch: list[str] = Field(default_factory=list)


class NextDayOpportunityPlan(BaseModel):
    focus_candidates: list[str] = Field(default_factory=list)
    position_discipline: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    avoid_conditions: list[str] = Field(default_factory=list)


class PracticalConclusion(BaseModel):
    headline: str
    bullet_points: list[str] = Field(default_factory=list)


class IndexMidTermOutlook(BaseModel):
    year_review: list[str] = Field(default_factory=list)
    current_position: str
    scenario_table: list[dict[str, str]] = Field(default_factory=list)


class StructuredSectorReview(BaseModel):
    sector: str
    headline: str
    stage: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    logic: str
    logic_points: list[str] = Field(default_factory=list)
    sustainability_analysis: str = ""
    sustainability: SustainabilityRating
    next_day_view: str
    watch_items: list[str] = Field(default_factory=list)
    avoid_items: list[str] = Field(default_factory=list)


class SustainabilityRank(BaseModel):
    rank: int
    sector: str
    rating: SustainabilityRating
    reason: str


class ActionDiscipline(BaseModel):
    focus: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    final_view: str


class StructuredReviewDTO(BaseModel):
    topic: str
    prediction_review: PredictionReview
    tomorrow_judgement: TomorrowJudgement
    market_overview: MarketOverviewTable
    after_hours_news: AfterHoursNewsSummary
    sector_reviews: list[StructuredSectorReview] = Field(default_factory=list)
    sustainability_ranking: list[SustainabilityRank] = Field(default_factory=list)
    capital_rotation: CapitalRotationPath
    next_day_opportunity: NextDayOpportunityPlan
    practical_conclusion: PracticalConclusion
    index_mid_term_outlook: IndexMidTermOutlook
    action_discipline: ActionDiscipline
