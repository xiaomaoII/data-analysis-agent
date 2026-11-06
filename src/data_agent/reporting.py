import json
from datetime import datetime, timezone

import plotly.graph_objects as go
from jinja2 import BaseLoader, Environment, select_autoescape

from data_agent.analysis import metric_value
from data_agent.models import BusinessReport
from data_agent.semantic import (
    ACTIONS,
    DIMENSIONS,
    HYPOTHESES,
    LIMITATIONS,
    METRIC_VERSION,
    METRICS,
)


def fmt(value, metric=None):
    if value is None:
        return "不可计算"
    return f"{value * 100:.3f}%" if metric == "gift_coverage" else f"{value:,.3f}"


def build_report(task, meta, mode, evidence, queries, narrative, run_info):
    known = {e.evidence_id for e in evidence}
    if (
        not narrative.highlight_evidence_ids
        or not set(narrative.highlight_evidence_ids) <= known
    ):
        raise ValueError("报告引用了不存在的证据，或未提供证据引用")
    metric = METRICS[task.metric]
    e = evidence[0]
    v = e.values
    if not task.baseline:
        summary = f"所选期间{metric['name']}为 {fmt(v['current'], task.metric)}。本次仅分析趋势，不做前后比较。"
    else:
        direction = {
            "up": "上升",
            "down": "下降",
            "flat": "持平",
            "unknown": "无法比较",
        }[v["direction"]]
        summary = f"{metric['name']}由 {fmt(v['baseline'], task.metric)} 变为 {fmt(v['current'], task.metric)}，{direction}。"
        if task.metric == "gift_coverage":
            summary += f"变化 {fmt(v['percentage_point_change'])} 个百分点。"
        else:
            summary += f"差值 {fmt(v['delta'])} {metric['unit']}。"
        summary += f"相对变化：{fmt(v['relative_change'], 'gift_coverage')}。"
        if "下降" in task.question and v["direction"] in {"up", "flat"}:
            summary += "数据没有支持问题中“下降”的前提。"
        if "上升" in task.question and v["direction"] in {"down", "flat"}:
            summary += "数据没有支持问题中“上升”的前提。"
    findings = [{"text": summary, "evidence_ids": ["E1"], "category": "已验证事实"}]
    coverage = evidence[1].values
    findings.append(
        {
            "text": f"当期未匹配同用户同日观看的送礼用户日为 {fmt(coverage['current_unmatched_users'])}，礼物价值为 {fmt(coverage['current_unmatched_value'])} 原始单位。",
            "evidence_ids": ["E2"],
            "category": "数据覆盖",
        }
    )
    # Selected highlights affect ordering; all exact numeric values are rendered by code.
    selected = [
        x
        for x in evidence
        if x.kind == "group_contribution"
        and x.evidence_id in narrative.highlight_evidence_ids
    ]
    if not selected:
        selected = [x for x in evidence if x.kind == "group_contribution"][:4]
    for item in selected:
        values = item.values
        findings.append(
            {
                "text": f"{DIMENSIONS[values['dimension']]} {values['group']} 的描述性贡献为 {fmt(values['contribution'])} {item.unit}。",
                "evidence_ids": [item.evidence_id],
                "category": "描述性贡献",
            }
        )
    return BusinessReport(
        title=metric["name"] + "业务分析报告",
        summary=summary,
        task=task,
        dataset_label=meta["label"],
        mode_label="离线固定响应演示（非真实模型）"
        if mode == "demo"
        else "DeepSeek 真实模型",
        metric_definition=metric["definition"],
        findings=findings,
        hypotheses=[HYPOTHESES[c] for c in dict.fromkeys(narrative.hypothesis_codes)],
        actions=[ACTIONS[c] for c in dict.fromkeys(narrative.action_codes)],
        limitations=LIMITATIONS,
        evidence=evidence,
        queries=queries,
        run_info={
            **run_info,
            "data_version": meta["data_version"],
            "metric_version": METRIC_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "timezone": "Asia/Shanghai",
        },
    )


def figures(report):
    daily = sorted(report.queries[0].rows, key=lambda r: r["activity_date"])
    fig = go.Figure(
        go.Scatter(
            x=[r["activity_date"] for r in daily],
            y=[
                (
                    metric_value(report.task.metric, r, 1) * 100
                    if report.task.metric == "gift_coverage" and r["watch_users"]
                    else metric_value(report.task.metric, r, 1)
                )
                for r in daily
            ],
            mode="lines+markers",
            name=METRICS[report.task.metric]["name"],
            connectgaps=False,
        )
    )
    fig.update_layout(
        title="每日趋势",
        template="plotly_white",
        yaxis_title=METRICS[report.task.metric]["unit"],
        xaxis_title="北京时间自然日",
    )
    # Insert missing calendar dates as None, rather than visually bridging gaps.
    from datetime import date, timedelta

    if daily:
        mapping = dict(zip(fig.data[0].x, fig.data[0].y))
        first, last = (
            date.fromisoformat(daily[0]["activity_date"]),
            date.fromisoformat(daily[-1]["activity_date"]),
        )
        days = [str(first + timedelta(days=i)) for i in range((last - first).days + 1)]
        fig.data[0].x, fig.data[0].y = days, [mapping.get(d) for d in days]
    result = {"trend": fig}
    for dim in DIMENSIONS:
        items = [
            e
            for e in report.evidence
            if e.kind == "group_contribution" and e.values["dimension"] == dim
        ]
        if items:
            chart = go.Figure(
                go.Bar(
                    x=[e.values["group"] for e in items],
                    y=[e.values["contribution"] for e in items],
                )
            )
            chart.update_layout(
                title=DIMENSIONS[dim] + "描述性贡献",
                template="plotly_white",
                yaxis_title=items[0].unit,
            )
            result[dim] = chart
    return result


def export_report(report, directory):
    directory.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    (directory / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    lines = [
        f"# {report.title}",
        "",
        f"**{report.dataset_label} · {report.mode_label}**",
        "",
        report.summary,
        "",
        "## 分析口径",
        "",
        report.metric_definition,
        "",
        f"当期：{report.task.current.start}—{report.task.current.end}",
        f"基期：{report.task.baseline.start}—{report.task.baseline.end}"
        if report.task.baseline
        else "基期：无，趋势模式",
        "",
        "## 已验证发现与描述性贡献",
        "",
    ]
    for finding in report.findings:
        lines.append(f"- {finding['text']} [{' / '.join(finding['evidence_ids'])}]")
    comparison = report.evidence[0].values
    component_rows = [
        ("完整日天数", comparison["baseline_days"], comparison["current_days"]),
        (
            "观看用户日（覆盖率分母）",
            comparison["baseline_components"]["watch_users"],
            comparison["current_components"]["watch_users"],
        ),
        (
            "观看且送礼用户日（覆盖率分子）",
            comparison["baseline_components"]["watch_gift_users"],
            comparison["current_components"]["watch_gift_users"],
        ),
        (
            "礼物总价值（原始单位）",
            comparison["baseline_components"]["gift_value"],
            comparison["current_components"]["gift_value"],
        ),
    ]
    lines.extend(
        [
            "",
            "## 分子、分母与总量 [E1]",
            "",
            "| 组成量 | 基期 | 当期 |",
            "|---|---:|---:|",
        ]
    )
    lines.extend(
        f"| {label} | {fmt(base) if report.task.baseline else '不适用'} | {fmt(current)} |"
        for label, base, current in component_rows
    )
    for title, items in [
        ("待验证解释", report.hypotheses),
        ("建议动作", report.actions),
        ("局限", report.limitations),
    ]:
        lines.extend(["", f"## {title}", ""] + [f"- {item}" for item in items])
    lines.extend(["", "## SQL 与证据", ""])
    for query in report.queries:
        lines.extend([f"### {query.query_id}", "", "```sql", query.sql, "```", ""])
    lines.extend(
        [
            "完整证据与运行版本见 report.json；交互图表见 report.html。",
            "",
            "```json",
            json.dumps(report.run_info, ensure_ascii=False, indent=2),
            "```",
        ]
    )
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")
    charts = figures(report)
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(default=True))
    template = env.from_string("""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{{ r.title }}</title><style>body{font-family:'Microsoft YaHei',system-ui,sans-serif;background:#f3f6fa;color:#183047;margin:0}main{max-width:1050px;margin:35px auto;padding:32px;background:white;border-radius:18px}h1{font-size:28px}h2{margin-top:32px}p,li{line-height:1.8}.badge{color:#176a66}pre{white-space:pre-wrap;background:#edf3f7;padding:16px;overflow-wrap:anywhere}small{color:#576b7a}</style>
    <main><p class="badge">{{r.dataset_label}} · {{r.mode_label}}</p><h1>{{r.title}}</h1><p>{{r.summary}}</p>
    <h2>指标与比较窗口</h2><p>{{r.metric_definition}}</p><p>当期 {{r.task.current.start}} 至 {{r.task.current.end}}{% if r.task.baseline %}；基期 {{r.task.baseline.start}} 至 {{r.task.baseline.end}}{% endif %}（北京时间）</p>
    <h2>分子、分母与总量 [E1]</h2><table style="border-collapse:collapse;width:100%;text-align:left"><tr><th>组成量</th><th>基期</th><th>当期</th></tr>{% for label,base,current in components %}<tr><td style="padding:8px">{{label}}</td><td>{{base}}</td><td>{{current}}</td></tr>{% endfor %}</table>
    {% for chart in charts %}{{chart|safe}}{% endfor %}<h2>证据支持的发现</h2><ul>{% for f in r.findings %}<li>{{f.text}} <small>[{{f.evidence_ids|join(', ')}}]</small></li>{% endfor %}</ul>
    {% for title,items in sections %}<h2>{{title}}</h2><ul>{% for item in items %}<li>{{item}}</li>{% endfor %}</ul>{% endfor %}
    <h2>查询证据</h2>{% for q in r.queries %}<details><summary>{{q.query_id}} · {{q.status}}</summary><pre>{{q.sql}}</pre></details>{% endfor %}
    <h2>数据与运行版本</h2><pre>{{run_info}}</pre></main></html>""")
    chart_html = [
        chart.to_html(full_html=False, include_plotlyjs=True if i == 0 else False)
        for i, chart in enumerate(charts.values())
    ]
    (directory / "report.html").write_text(
        template.render(
            r=report,
            charts=chart_html,
            components=[
                (label, fmt(base) if report.task.baseline else "不适用", fmt(current))
                for label, base, current in component_rows
            ],
            sections=[
                ("待验证解释", report.hypotheses),
                ("建议动作", report.actions),
                ("限制", report.limitations),
            ],
            run_info=json.dumps(report.run_info, ensure_ascii=False, indent=2),
        ),
        encoding="utf-8",
    )
    import pandas as pd

    for query in report.queries:
        pd.DataFrame(query.rows).to_csv(
            directory / f"{query.query_id}.csv", index=False, encoding="utf-8-sig"
        )
    return ["report.json", "report.md", "report.html"] + [
        f"{q.query_id}.csv" for q in report.queries
    ]
