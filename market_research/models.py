from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    role: Literal["date", "numeric", "categorical", "identifier", "text"]
    missing_pct: float
    sample_values: list[str]
    stats: dict = Field(default_factory=dict)


class TimelineInfo(BaseModel):
    has_timeline: bool
    date_column: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class DataProfile(BaseModel):
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    description: str
    description_was_generated: bool
    domain: str
    timeline: TimelineInfo


class SourceRef(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None


class KeyFinding(BaseModel):
    title: str
    detail: str
    sources: list[SourceRef] = Field(default_factory=list)


class Recommendation(BaseModel):
    recommendation: str
    rationale: str
    priority: Literal["high", "medium", "low"] = "medium"


class MarketResearchReport(BaseModel):
    mode: Literal["time_bounded", "column_context"]
    executive_summary: str
    domain: str
    timeline: TimelineInfo
    key_findings: list[KeyFinding]
    opportunities: list[str]
    risks: list[str]
    recommendations: list[Recommendation]
    sources: list[SourceRef]


class DagNode(BaseModel):
    id: str
    label: str
    type: Literal["dataset_variable", "external_factor"]
    description: Optional[str] = None


class DagEdge(BaseModel):
    source: str
    target: str
    relationship: str
    rationale: str
    confidence: Literal["high", "medium", "low"] = "medium"


class CausalDag(BaseModel):
    nodes: list[DagNode]
    edges: list[DagEdge]


class AnalysisResult(BaseModel):
    data_profile: DataProfile
    market_research: MarketResearchReport
    dag: Optional[CausalDag] = None
    dag_unavailable_reason: Optional[str] = None
