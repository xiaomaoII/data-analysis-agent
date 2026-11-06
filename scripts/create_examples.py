"""Generate and index examples without any paid model request."""

import argparse
import json
import shutil

from data_agent.config import Settings
from data_agent.evaluation.cases import CASES
from data_agent.models import AnalysisRequest
from data_agent.orchestration import Analyst


def main():
    parser = argparse.ArgumentParser(description="Generate explicit offline examples")
    parser.add_argument(
        "--dataset", choices=["synthetic", "kuailive_dev"], default="synthetic"
    )
    args = parser.parse_args()
    settings = Settings.load()
    output = settings.root / "reports" / "examples"
    output.mkdir(parents=True, exist_ok=True)
    items = []
    for dataset in [args.dataset]:
        for i, slug in [
            (0, "gift-coverage"),
            (4, "viewer-activity"),
            (8, "gift-value"),
        ]:
            run_id = f"example-{dataset}-{slug}"
            result = Analyst(
                settings,
                AnalysisRequest(
                    question=CASES[i]["question"], dataset_id=dataset, mode="demo"
                ),
                run_id,
            ).run()
            if result["status"] != "completed":
                raise RuntimeError(result.get("error", result["status"]))
            folder = output / f"{dataset}-{slug}"
            folder.mkdir(exist_ok=True)
            for name in result["artifacts"]:
                shutil.copy2(
                    settings.root / "reports" / "runs" / run_id / name, folder / name
                )
            items.append(
                {
                    "dataset": dataset,
                    "metric": slug,
                    "status": result["status"],
                    "summary": result["report"]["summary"],
                    "html": f"{folder.name}/report.html",
                }
            )
    (output / "index.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    links = "\n".join(
        f'<li><a href="{i["html"]}">{i["dataset"]} / {i["metric"]}</a></li>'
        for i in items
    )
    (output / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Data Agent 样例报告</title><style>body{font:18px Microsoft YaHei,sans-serif;max-width:900px;margin:60px auto;line-height:2;color:#17324d}a{color:#147d78}</style><h1>业务分析样例</h1><p>全部由离线固定响应流程生成；KuaiLive 样例使用真实开发期数据，但不代表真实模型验收。</p><ul>'
        + links
        + "</ul>",
        encoding="utf-8",
    )
    print(json.dumps(items, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
