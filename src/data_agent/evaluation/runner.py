import json
import uuid
from datetime import datetime, timezone

from data_agent.evaluation.cases import CASES
from data_agent.models import AnalysisRequest
from data_agent.orchestration import Analyst


def evaluate(settings, mode="demo", dataset_id="synthetic"):
    records = []
    for case in CASES:
        request = AnalysisRequest(
            question=case["question"], mode=mode, dataset_id=dataset_id
        )
        result = Analyst(settings, request, "eval_" + uuid.uuid4().hex).run()
        task = result.get("task", {})
        metric_ok = (
            not case["expected_metric"]
            or result["status"] != "completed"
            or task.get("metric") == case["expected_metric"]
        )
        report = result.get("report", {})
        evidence_ids = {e["evidence_id"] for e in result.get("evidence", [])}
        grounded = all(
            set(f["evidence_ids"]) <= evidence_ids and f["evidence_ids"]
            for f in report.get("findings", [])
        )
        correct_queries = all(
            q["status"] == "verified" for q in result.get("queries", [])
        )
        window_ok = result["status"] != "completed" or (
            task.get("current") == {"start": "2025-05-12", "end": "2025-05-17"}
            and task.get("baseline") == {"start": "2025-05-06", "end": "2025-05-11"}
        )
        passed = (
            result["status"] == case["expected_status"]
            and metric_ok
            and window_ok
            and grounded
            and correct_queries
        )
        records.append(
            {
                "case_id": case["id"],
                "question": case["question"],
                "category": case["category"],
                "expected_status": case["expected_status"],
                "actual_status": result["status"],
                "metric_correct": metric_ok,
                "window_correct": window_ok,
                "query_results_verified": correct_queries,
                "evidence_grounded": grounded,
                "passed": passed,
                "run_id": result["run_id"],
                "budget": result["budget"],
                "error": result.get("error"),
            }
        )
    payload = {
        "mode": mode,
        "dataset_id": dataset_id,
        "label": "固定响应流程回归（不代表模型能力）"
        if mode == "demo"
        else "真实模型项目内评测",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "passed": sum(r["passed"] for r in records),
        "total": len(records),
        "live_acceptance": "not_run"
        if mode == "demo"
        else "requires_hard_gate_test_results",
        "cases": records,
    }
    output = settings.root / "reports" / f"evaluation_{mode}.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload
