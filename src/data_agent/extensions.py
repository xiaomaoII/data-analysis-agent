"""Contracts for later releases. No implementation or completed capability is claimed."""

from typing import Protocol

from data_agent.models import AnalysisTask, BusinessReport


class MemoryStore(Protocol):
    def load_confirmed_task(
        self, conversation_id: str, data_version: str, metric_version: str
    ) -> AnalysisTask | None: ...
    def save_confirmed_task(
        self,
        conversation_id: str,
        task: AnalysisTask,
        data_version: str,
        metric_version: str,
    ) -> None: ...


class MLAnalyzer(Protocol):
    def analyze(self, task: AnalysisTask, approved_model_version: str) -> dict: ...


class ExperimentAdvisor(Protocol):
    def propose(self, report: BusinessReport, design_inputs: dict) -> dict: ...
