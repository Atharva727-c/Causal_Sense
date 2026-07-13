"""Top-level entry point: MarketResearchAgent ties together data profiling,
web-research synthesis, and causal DAG generation into a single call a REST
endpoint can invoke directly."""

from __future__ import annotations

from .dag_builder import build_causal_dag
from .data_profiler import FileInput, build_data_profile
from .models import AnalysisResult
from .research_agent import run_market_research


class MarketResearchAgent:
    def analyze(self, file: FileInput, description: str | None = None, filename: str | None = None) -> AnalysisResult:
        profile = build_data_profile(file, description=description, filename=filename)
        report = run_market_research(profile)
        dag, dag_unavailable_reason = build_causal_dag(profile, report)

        return AnalysisResult(
            data_profile=profile,
            market_research=report,
            dag=dag,
            dag_unavailable_reason=dag_unavailable_reason,
        )


def analyze_file(file: FileInput, description: str | None = None, filename: str | None = None) -> AnalysisResult:
    return MarketResearchAgent().analyze(file, description=description, filename=filename)
