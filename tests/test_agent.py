import uuid
from dataclasses import replace

import httpx
import pytest

from data_agent.config import Settings
from data_agent.database.prepare import prepare
from data_agent.evaluation.cases import CASES
from data_agent.llm import Budget, BudgetExceeded, DeepSeek, FixtureModel
from data_agent.models import AnalysisRequest, Intent, Narrative, SQLResponse
from data_agent.orchestration import Analyst


def run(settings, index=0, **kwargs):
    req = AnalysisRequest(question=CASES[index]["question"], mode="demo", **kwargs)
    return Analyst(settings, req, uuid.uuid4().hex).run()


@pytest.mark.parametrize("index", [0, 4, 8])
def test_three_full_workflows(settings, index):
    result = run(settings, index)
    assert result["status"] == "completed", result.get("error")
    assert len(result["queries"]) == 3
    assert set(result["dimensions_used"]) == {"age", "gender"}
    assert result["budget"]["model_calls"] == 0
    assert "非真实模型" in result["report"]["mode_label"]
    ids = {e["evidence_id"] for e in result["evidence"]}
    for finding in result["report"]["findings"]:
        assert set(finding["evidence_ids"]) <= ids
    for filename in result["artifacts"]:
        assert (
            settings.root / "reports" / "runs" / result["run_id"] / filename
        ).exists()


@pytest.mark.parametrize("index", range(12, 24))
def test_clarifications_and_boundaries(settings, index):
    result = run(settings, index)
    assert result["status"] == CASES[index]["expected_status"], result.get("error")
    if result["status"] == "needs_clarification":
        assert not result["queries"]


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("flat", "completed"),
        ("zero", "insufficient_evidence"),
        ("missing", "needs_clarification"),
    ],
)
def test_edge_data(tmp_path, scenario, expected):
    settings = Settings(root=tmp_path)
    prepare(settings, scenario=scenario)
    result = run(settings)
    assert result["status"] == expected, result.get("error")
    if scenario == "flat":
        assert result["evidence"][0]["values"]["delta"] == 0
        assert len(result["queries"]) == 1


def test_false_decline_corrected_and_zero_baseline(tmp_path):
    settings = Settings(root=tmp_path)
    prepare(settings, scenario="increase")
    result = run(settings, 22)
    assert result["status"] == "completed", result.get("error")
    assert "没有支持" in result["report"]["summary"]
    prepare(settings, scenario="baseline_zero")
    result = run(settings, 8)
    assert result["status"] == "completed", result.get("error")
    assert result["evidence"][0]["values"]["relative_change"] is None


def test_missing_key_is_not_silently_demo(settings):
    req = AnalysisRequest(question=CASES[0]["question"], mode="live")
    result = Analyst(settings, req, uuid.uuid4().hex).run()
    assert result["status"] == "failed"
    assert "DEEPSEEK_API_KEY" in result["error"]
    assert not result.get("report")


@pytest.mark.parametrize(
    "body",
    [
        {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
        {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": "{bad"}}]},
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"metric":"invented"}'},
                }
            ]
        },
    ],
)
def test_invalid_model_output_bounded(settings, body):
    config = replace(settings, api_key="test-only")
    budget = Budget(config)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    )
    model = DeepSeek(config, budget, client)
    try:
        with pytest.raises(ValueError):
            model.call("intent", {}, Intent)
        assert budget.model_calls == 2
    finally:
        model.close()


@pytest.mark.parametrize("status", [429, 500, 401])
def test_provider_status_no_secret_disclosure(settings, status):
    config = replace(settings, api_key="test-secret-never-log")
    budget = Budget(config)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, json={"error": "test-secret-never-log"}
            )
        )
    )
    model = DeepSeek(config, budget, client)
    try:
        with pytest.raises(ValueError) as err:
            model.call("intent", {}, Intent)
        assert "test-secret" not in str(err.value)
        assert budget.model_calls == (1 if status == 401 else 2)
    finally:
        model.close()


def test_sql_and_time_budgets(settings):
    result = run(replace(settings, max_sql_attempts=0))
    assert result["status"] == "failed"
    assert "预算" in result["error"]
    result = run(replace(settings, run_timeout=0.00001))
    assert result["status"] == "failed"
    budget = Budget(
        replace(settings, max_model_calls=1),
        previous={"model_calls": 1, "elapsed_seconds": 0.1},
    )
    with pytest.raises(BudgetExceeded):
        budget.model()


def test_model_request_has_total_wall_clock_timeout(settings):
    import asyncio
    import time

    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    config = replace(settings, api_key="test-only", model_timeout=0.02)
    budget = Budget(config)
    model = DeepSeek(
        config, budget, httpx.AsyncClient(transport=httpx.MockTransport(slow))
    )
    started = time.monotonic()
    try:
        with pytest.raises(ValueError):
            model.call("intent", {}, Intent)
        assert time.monotonic() - started < 0.5
        assert budget.model_calls == 2
    finally:
        model.close()


def test_bad_sql_repaired_once_and_no_evidence_fabricated(settings):
    class RepairModel(FixtureModel):
        def call(self, kind, context, schema):
            if schema is SQLResponse and not context.get("previous_error"):
                return SQLResponse(sql="SELECT invented FROM daily_metrics")
            return super().call(kind, context, schema)

    req = AnalysisRequest(question=CASES[0]["question"], mode="demo")
    result = Analyst(
        settings,
        req,
        uuid.uuid4().hex,
        provider_factory=lambda s, b: RepairModel(s, b, CASES[0]["intent"]),
    ).run()
    assert result["status"] == "completed", result.get("error")
    assert result["budget"]["sql_attempts"] == 6

    class BadReport(FixtureModel):
        def call(self, kind, context, schema):
            if schema is Narrative:
                return Narrative(
                    highlight_evidence_ids=["E999"],
                    hypothesis_codes=[],
                    action_codes=[],
                )
            return super().call(kind, context, schema)

    result = Analyst(
        settings,
        req,
        uuid.uuid4().hex,
        provider_factory=lambda s, b: BadReport(s, b, CASES[0]["intent"]),
    ).run()
    assert result["status"] == "failed"
    assert result["evidence"]
    assert not result.get("report")
    assert result["artifacts"] == ["evidence.json"]
