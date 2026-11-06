from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Metric = Literal["gift_coverage", "avg_viewers", "gift_value"]
Dimension = Literal["age", "gender"]
Status = Literal[
    "queued",
    "running",
    "needs_clarification",
    "completed",
    "insufficient_evidence",
    "failed",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Window(StrictModel):
    start: date
    end: date  # inclusive in all public interfaces

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class AnalysisRequest(StrictModel):
    question: str = Field(min_length=2, max_length=2000)
    dataset_id: Literal["synthetic", "kuailive_dev"] = "synthetic"
    mode: Literal["demo", "live"] = "live"
    metric: Metric | None = None
    current: Window | None = None
    baseline: Window | None = None
    trend_only: bool = False


class Clarification(StrictModel):
    metric: Metric | None = None
    current: Window | None = None
    baseline: Window | None = None
    trend_only: bool = False


class Intent(StrictModel):
    metric: Metric | None
    current: Window | None = None
    baseline: Window | None = None
    days: int | None = Field(default=None, ge=1, le=31)
    trend_only: bool = False
    unsupported_reason: str | None = None
    clarification: str | None = None


class AnalysisTask(StrictModel):
    question: str
    metric: Metric
    current: Window
    baseline: Window | None
    trend_only: bool = False
    dimensions: list[Dimension] = Field(default_factory=lambda: ["age", "gender"])
    assumptions: list[str] = Field(default_factory=list)


class SQLResponse(StrictModel):
    sql: str = Field(min_length=1, max_length=16000)


class DrillDecision(StrictModel):
    dimension: Dimension | None
    reason: Literal[
        "inspect_group_contribution",
        "compare_second_dimension",
        "no_material_change",
        "enough_evidence",
        "no_comparison",
    ]


class Narrative(StrictModel):
    # Model selects evidence and bounded interpretation/action codes, never numbers or prose claims.
    highlight_evidence_ids: list[str] = Field(max_length=8)
    hypothesis_codes: list[
        Literal[
            "composition_or_within_group",
            "calendar_or_collection",
            "gift_concentration_unknown",
        ]
    ] = Field(max_length=3)
    action_codes: list[
        Literal["check_collection", "review_group_context", "design_controlled_test"]
    ] = Field(max_length=3)


class QueryResult(StrictModel):
    query_id: str
    sql: str
    parameters: dict = Field(default_factory=dict)
    columns: list[str]
    rows: list[dict]
    data_version: str
    dimension: Dimension | None = None
    status: str = "verified"
    elapsed_seconds: float


class EvidenceItem(StrictModel):
    evidence_id: str
    kind: Literal["comparison", "group_contribution", "coverage", "trend"]
    metric: str
    unit: str
    values: dict
    query_ids: list[str]


class BusinessReport(StrictModel):
    title: str
    summary: str
    task: AnalysisTask
    dataset_label: str
    mode_label: str
    metric_definition: str
    findings: list[dict]
    hypotheses: list[str]
    actions: list[str]
    limitations: list[str]
    evidence: list[EvidenceItem]
    queries: list[QueryResult]
    run_info: dict
