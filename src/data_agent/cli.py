import argparse
import json
import uuid

from data_agent.config import Settings


def main():
    parser = argparse.ArgumentParser(
        description="Data Analysis Agent：显式准备、分析、评测与启动"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument(
        "--dataset", choices=["synthetic", "kuailive_dev"], default="synthetic"
    )
    prep.add_argument("--source")
    prep.add_argument(
        "--scenario",
        default="change",
        choices=["change", "flat", "zero", "missing", "increase", "baseline_zero"],
    )
    analyze = sub.add_parser("analyze")
    analyze.add_argument("question")
    analyze.add_argument(
        "--dataset", default="synthetic", choices=["synthetic", "kuailive_dev"]
    )
    analyze.add_argument("--mode", default="live", choices=["live", "demo"])
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--mode", default="demo", choices=["demo", "live"])
    evaluate.add_argument(
        "--dataset", default="synthetic", choices=["synthetic", "kuailive_dev"]
    )
    sub.add_parser("serve")
    sub.add_parser("doctor")
    args = parser.parse_args()
    settings = Settings.load()
    if args.command == "prepare":
        from data_agent.database.prepare import prepare

        result = prepare(settings, args.dataset, args.source, args.scenario)
    elif args.command == "analyze":
        from data_agent.models import AnalysisRequest
        from data_agent.orchestration import Analyst

        result = Analyst(
            settings,
            AnalysisRequest(
                question=args.question, dataset_id=args.dataset, mode=args.mode
            ),
            uuid.uuid4().hex,
        ).run()
        result = {
            "run_id": result["run_id"],
            "status": result["status"],
            "summary": result.get("report", {}).get("summary"),
            "error": result.get("error"),
            "artifacts": result.get("artifacts"),
            "clarification": result.get("clarification"),
        }
    elif args.command == "evaluate":
        from data_agent.evaluation.runner import evaluate

        result = evaluate(settings, args.mode, args.dataset)
        result = {k: v for k, v in result.items() if k != "cases"}
    elif args.command == "serve":
        import uvicorn

        from data_agent.api import create_app

        uvicorn.run(create_app(settings), host="127.0.0.1", port=8000, workers=1)
        return
    else:
        result = {
            "project_root": str(settings.root),
            "live_configured": bool(settings.api_key),
            "model": settings.model,
            "datasets": {
                name: settings.database(name).exists()
                for name in ["synthetic", "kuailive_dev"]
            },
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
