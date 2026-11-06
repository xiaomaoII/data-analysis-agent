import json
import re
from datetime import date, timedelta
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from data_agent.database.prepare import metadata
from data_agent.database.query import expected_columns
from data_agent.llm import Budget, DeepSeek, FixtureModel
from data_agent.models import (
    AnalysisTask,
    DrillDecision,
    Intent,
    Narrative,
    SQLResponse,
    Window,
)
from data_agent.reporting import build_report, export_report
from data_agent.semantic import DIMENSIONS, METRICS
from data_agent.tools import AnalysisTools


class RunState(TypedDict, total=False):
    status: str
    task: AnalysisTask
    clarification: dict
    queries: list
    evidence: list
    dimensions_used: list
    next_dimension: str | None
    report: object
    artifacts: list
    error: str


def fixture_intent(question):
    from data_agent.evaluation.cases import CASES

    for case in CASES:
        if case["question"] == question:
            return case["intent"]
    raise ValueError("离线演示仅支持页面示例和内置评测题；自由提问请使用真实模型模式")


class Analyst:
    def __init__(
        self,
        settings,
        request,
        run_id,
        on_event=None,
        provider_factory=None,
        previous_budget=None,
    ):
        self.settings, self.request, self.run_id = settings, request, run_id
        self.on_event = on_event or (lambda event: None)
        self.provider_factory = provider_factory
        self.budget = Budget(settings, previous_budget)
        self.trace = []
        self.model = None
        self.tools = AnalysisTools(settings)
        self.state = {"queries": [], "evidence": [], "dimensions_used": []}

    def event(self, stage, **details):
        item = {"stage": stage, **details, **self.budget.snapshot()}
        self.trace.append(item)
        self.on_event(item)

    def resolve(self, state):
        self.event("understand")
        req = self.request
        for token in [
            r"\b(?:DROP|DELETE|INSERT|UPDATE|ATTACH|COPY|INSTALL|LOAD)\b",
            r"read_(?:csv|parquet|text)",
            r"(?:读取|泄露|显示).{0,12}(?:密钥|环境变量|本地文件)",
        ]:
            if re.search(token, req.question, re.I):
                return {
                    "status": "insufficient_evidence",
                    "error": "该请求超出业务分析工具范围，不执行文件、密钥或写入操作。",
                }
        if req.metric is None and "付费率" in req.question:
            return self.clarify("当前数据只支持观看用户送礼覆盖率，是否采用这一口径？")
        if self.provider_factory:
            self.model = self.provider_factory(self.settings, self.budget)
        elif req.mode == "live":
            self.model = DeepSeek(self.settings, self.budget)
        else:
            self.model = FixtureModel(
                self.settings, self.budget, fixture_intent(req.question)
            )
        intent = self.model.call(
            "Interpret business task; unsupported dimensions (city/channel/ROI/LTV) require unsupported_reason. Ambiguous payment metric needs clarification. Relative dates use dataset end, not today's date.",
            {
                "question": req.question,
                "explicit_request": req.model_dump(mode="json"),
                "metrics": METRICS,
                "dimensions": DIMENSIONS,
                "dataset_start": self.meta["start"],
                "dataset_end": self.meta["end"],
            },
            Intent,
        )
        if intent.unsupported_reason:
            return {
                "status": "insufficient_evidence",
                "error": intent.unsupported_reason,
            }
        if intent.clarification and not req.metric and not req.current:
            return self.clarify(intent.clarification)
        literal_dates = re.findall(r"\d{4}-\d{2}-\d{2}", req.question)
        if len(literal_dates) == 2 and not req.current:
            if (
                not intent.current
                or [str(intent.current.start), str(intent.current.end)] != literal_dates
            ):
                return self.clarify(
                    "模型理解的日期与问题中的明确日期不一致，请确认窗口。"
                )
        metric = req.metric or intent.metric
        if not metric:
            return self.clarify("请明确要分析送礼覆盖率、日均观看人数还是礼物价值。")
        days = intent.days or 6
        current = (
            req.current
            or intent.current
            or Window(
                start=date.fromisoformat(self.meta["end"]) - timedelta(days=days - 1),
                end=date.fromisoformat(self.meta["end"]),
            )
        )
        trend_only = req.trend_only or intent.trend_only
        baseline = (
            None
            if trend_only
            else req.baseline
            or intent.baseline
            or Window(
                start=current.start
                - timedelta(days=(current.end - current.start).days + 1),
                end=current.start - timedelta(days=1),
            )
        )
        if baseline and baseline.end >= current.start:
            return self.clarify("基期必须在当期之前且不能重叠。")
        if baseline and (baseline.end - baseline.start) != (
            current.end - current.start
        ):
            return self.clarify("请提供长度相同的完整比较窗口，或选择只看趋势。")
        available = set(self.meta["complete_dates"])
        for window in [current] + ([baseline] if baseline else []):
            if (window.end - window.start).days > 30:
                return self.clarify("首版仅支持可用范围内的短窗口分析。")
            dates = {
                str(window.start + timedelta(days=i))
                for i in range((window.end - window.start).days + 1)
            }
            if not dates <= available:
                return self.clarify(
                    "所选窗口包含不可用或不完整日期，请修改窗口或仅分析有完整数据的趋势。"
                )
        task = AnalysisTask(
            question=req.question,
            metric=metric,
            current=current,
            baseline=baseline,
            trend_only=trend_only,
            assumptions=[
                "最近相对于数据集最后完整日",
                "日期端点均包含在内",
                "多日送礼覆盖采用用户日加权口径",
            ],
        )
        self.event("task_confirmed", task=task.model_dump(mode="json"))
        return {"task": task, "status": "running"}

    def clarify(self, reason):
        end = date.fromisoformat(self.meta["end"])
        return {
            "status": "needs_clarification",
            "clarification": {
                "reason": reason,
                "metrics": METRICS,
                "suggested_current": {
                    "start": str(end - timedelta(days=5)),
                    "end": str(end),
                },
                "suggested_baseline": {
                    "start": str(end - timedelta(days=11)),
                    "end": str(end - timedelta(days=6)),
                },
                "allowed_start": self.meta["start"],
                "allowed_end": self.meta["end"],
            },
        }

    def query(self, state, dimension=None):
        error = None
        for attempt in range(2):
            context = {
                "task": state["task"].model_dump(mode="json"),
                "dimension": dimension,
                "table": "daily_segment_metrics" if dimension else "daily_metrics",
                "required_columns_in_order": expected_columns(dimension),
                "previous_error": error,
                "rules": "Return all daily rows in exactly the confirmed window(s), inclusive DATE literals. Select listed columns in order. Single SELECT or nonrecursive CTE; no functions, joins, arithmetic or aggregation. For segment query filter exactly the specified dimension. These tables already contain daily counts and values. Do not limit or omit rows.",
            }
            generated = self.model.call(
                "Generate DuckDB SQL following the query contract.",
                context,
                SQLResponse,
            )
            self.budget.sql()
            self.event(
                "sql_validation",
                dimension=dimension,
                attempt=attempt + 1,
                sql=generated.sql,
            )
            try:
                result = self.tools.query_daily_metrics(
                    self.request.dataset_id,
                    state["task"],
                    generated.sql,
                    f"Q{len(state['queries']) + 1}",
                    self.meta["data_version"],
                    dimension,
                    timeout=min(self.settings.sql_timeout, self.budget.remaining()),
                )
                self.event(
                    "query_verified",
                    query_id=result.query_id,
                    dimension=dimension,
                    rows=len(result.rows),
                )
                return result
            except (ValueError, TimeoutError) as exc:
                error = str(exc)
                self.event("query_rejected", reason=error, dimension=dimension)
        raise ValueError("SQL 修复后仍未通过：" + error)

    def overall(self, state):
        query = self.query(state)
        evidence = self.tools.compare_periods(state["task"], query)
        self.state.update(task=state["task"], queries=[query], evidence=evidence)
        if evidence[0].values["current"] is None or (
            state["task"].baseline and evidence[0].values["baseline"] is None
        ):
            return {
                "queries": [query],
                "evidence": evidence,
                "status": "insufficient_evidence",
                "error": "比较窗口没有有效分母，无法计算该指标。",
            }
        return {"queries": [query], "evidence": evidence}

    def decide(self, state):
        available = [
            d for d in state["task"].dimensions if d not in state["dimensions_used"]
        ]
        if not available or not state["task"].baseline:
            return {"next_dimension": None}
        decision = self.model.call(
            "Choose one unused dimension for further descriptive diagnosis, or stop. Unknown/flat overall change should stop. Never claim a causal explanation.",
            {
                "available_dimensions": available,
                "direction": state["evidence"][0].values["direction"],
                "evidence": [e.model_dump(mode="json") for e in state["evidence"]],
            },
            DrillDecision,
        )
        if decision.dimension and decision.dimension not in available:
            raise ValueError("模型重复选择了维度或选择了不支持的工具")
        self.event(
            "drill_decision", dimension=decision.dimension, reason=decision.reason
        )
        return {"next_dimension": decision.dimension}

    def drill(self, state):
        query = self.query(state, state["next_dimension"])
        extra = self.tools.group_contributions(
            state["task"], state["evidence"][0], query, len(state["evidence"]) + 1
        )
        update = {
            "queries": state["queries"] + [query],
            "evidence": state["evidence"] + extra,
            "dimensions_used": state["dimensions_used"] + [state["next_dimension"]],
        }
        self.state.update(update)
        return update

    def report(self, state):
        narrative = self.model.call(
            "Select evidence IDs, hypotheses and actions from supported codes. Hypotheses are unverified. Return no invented facts.",
            {
                "evidence_ids": [e.evidence_id for e in state["evidence"]],
                "evidence": [e.model_dump(mode="json") for e in state["evidence"]],
            },
            Narrative,
        )
        self.budget.remaining()
        report = build_report(
            state["task"],
            self.meta,
            self.request.mode,
            state["evidence"],
            state["queries"],
            narrative,
            {
                "run_id": self.run_id,
                "model": self.settings.model
                if self.request.mode == "live"
                else "fixture-v1",
                **self.budget.snapshot(),
            },
        )
        artifacts = export_report(report, self.directory)
        self.budget.remaining()
        self.event("report_completed")
        return {"status": "completed", "report": report, "artifacts": artifacts}

    def run(self):
        self.directory = self.settings.root / "reports" / "runs" / self.run_id
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            self.meta = metadata(self.settings, self.request.dataset_id)
            graph = StateGraph(RunState)
            for name, func in [
                ("resolve", self.resolve),
                ("overall", self.overall),
                ("decide", self.decide),
                ("drill", self.drill), 
                ("report", self.report),
            ]:
                graph.add_node(name, func)
            graph.add_edge(START, "resolve")
            graph.add_conditional_edges(
                "resolve", lambda s: "overall" if s["status"] == "running" else END
            )
            graph.add_conditional_edges(
                "overall",
                lambda s: END if s["status"] == "insufficient_evidence" else "decide",
            )
            graph.add_conditional_edges(
                "decide", lambda s: "drill" if s.get("next_dimension") else "report"
            )
            graph.add_edge("drill", "decide")
            graph.add_edge("report", END)
            self.state = graph.compile().invoke(
                {
                    "status": "running",
                    "queries": [],
                    "evidence": [],
                    "dimensions_used": [],
                },
                config={"recursion_limit": 20},
            )
        except Exception as exc:
            self.state.update(status="failed", error=str(exc))
            self.event("failed", message=str(exc))
        finally:
            if self.model:
                self.model.close()
        result = {key: serialize(value) for key, value in self.state.items()}
        result.update(
            run_id=self.run_id,
            request=self.request.model_dump(mode="json"),
            trace=self.trace,
            budget=self.budget.snapshot(),
        )
        (self.directory / "evidence.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        result["artifacts"] = result.get("artifacts", []) + ["evidence.json"]
        return result


def serialize(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value
