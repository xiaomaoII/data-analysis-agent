import math

from data_agent.models import EvidenceItem
from data_agent.semantic import COMPONENTS, METRICS


def period_rows(rows, window):
    return [
        r for r in rows if str(window.start) <= r["activity_date"] <= str(window.end)
    ]


def totals(rows):
    return {col: sum(r[col] for r in rows) for col in COMPONENTS}


def metric_value(metric, sums, days):
    if metric == "gift_coverage":
        return (
            sums["watch_gift_users"] / sums["watch_users"]
            if sums["watch_users"]
            else None
        )
    if metric == "avg_viewers":
        return sums["watch_users"] / days if days else None
    return sums["gift_value"]


def compare(task, query):
    current = period_rows(query.rows, task.current)
    baseline = period_rows(query.rows, task.baseline) if task.baseline else []
    cur_sum, base_sum = totals(current), totals(baseline)
    cur_value = metric_value(task.metric, cur_sum, len(current))
    base_value = (
        metric_value(task.metric, base_sum, len(baseline)) if baseline else None
    )
    delta = (
        cur_value - base_value
        if cur_value is not None and base_value is not None
        else None
    )
    values = {
        "current": cur_value,
        "baseline": base_value,
        "delta": delta,
        "percentage_point_change": delta * 100
        if delta is not None and task.metric == "gift_coverage"
        else None,
        "relative_change": delta / base_value
        if delta is not None and base_value
        else None,
        "direction": "unknown"
        if delta is None
        else "flat"
        if math.isclose(delta, 0, abs_tol=1e-12)
        else "up"
        if delta > 0
        else "down",
        "current_components": cur_sum,
        "baseline_components": base_sum,
        "current_days": len(current),
        "baseline_days": len(baseline),
    }
    evidence = [
        EvidenceItem(
            evidence_id="E1",
            kind="comparison" if baseline else "trend",
            metric=task.metric,
            unit=METRICS[task.metric]["unit"],
            values=values,
            query_ids=[query.query_id],
        )
    ]
    evidence.append(
        EvidenceItem(
            evidence_id="E2",
            kind="coverage",
            metric="unmatched_gifts",
            unit="用户日 / 原始礼物价值单位",
            values={
                "current_unmatched_users": cur_sum["unmatched_gift_users"],
                "current_unmatched_value": cur_sum["unmatched_gift_value"],
                "baseline_unmatched_users": base_sum["unmatched_gift_users"],
                "baseline_unmatched_value": base_sum["unmatched_gift_value"],
            },
            query_ids=[query.query_id],
        )
    )
    return evidence


def contributions(task, overall, query, start_id):
    values = overall.values
    if values["delta"] is None:
        return []
    groups = sorted({r["segment_value"] for r in query.rows})
    result = []
    for group in groups:
        rows = [r for r in query.rows if r["segment_value"] == group]
        cur, base = (
            totals(period_rows(rows, task.current)),
            totals(period_rows(rows, task.baseline)),
        )
        if task.metric == "gift_coverage":
            c = cur["watch_gift_users"] / values["current_components"]["watch_users"]
            b = base["watch_gift_users"] / values["baseline_components"]["watch_users"]
            unit = "百分点"
            contribution = (c - b) * 100
        elif task.metric == "avg_viewers":
            contribution = (
                cur["watch_users"] / values["current_days"]
                - base["watch_users"] / values["baseline_days"]
            )
            unit = "人/日"
        else:
            contribution = cur["gift_value"] - base["gift_value"]
            unit = "原始礼物价值单位"
        result.append(
            EvidenceItem(
                evidence_id=f"E{start_id + len(result)}",
                kind="group_contribution",
                metric=task.metric,
                unit=unit,
                values={
                    "dimension": query.dimension,
                    "group": group,
                    "contribution": contribution,
                    "current_components": cur,
                    "baseline_components": base,
                },
                query_ids=[overall.query_ids[0], query.query_id],
            )
        )
    expected = values["delta"] * (100 if task.metric == "gift_coverage" else 1)
    if not math.isclose(
        sum(e.values["contribution"] for e in result),
        expected,
        abs_tol=1e-8,
        rel_tol=1e-9,
    ):
        raise ValueError("分组贡献之和无法还原整体变化")
    return sorted(result, key=lambda e: abs(e.values["contribution"]), reverse=True)
