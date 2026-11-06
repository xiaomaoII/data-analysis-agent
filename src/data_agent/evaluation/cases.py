CASES = []


def add(question, metric=None, status="completed", category="normal", **intent):
    CASES.append(
        {
            "id": f"C{len(CASES) + 1:02d}",
            "question": question,
            "expected_metric": metric,
            "expected_status": status,
            "category": category,
            "intent": {"metric": metric, **intent},
        }
    )


for question in [
    "最近六天观看用户的送礼覆盖率是否下降？哪些群体贡献较大？",
    "比较最近六天与前六天的观看用户送礼覆盖率",
    "送礼覆盖率变化主要来自哪些年龄原始分组码？",
    "查看观看用户送礼覆盖率趋势及性别分组贡献",
]:
    add(question, "gift_coverage")
for question in [
    "最近六天日均观看人数发生了什么变化？",
    "比较前后两个六日窗口的观看活跃情况",
    "哪些性别分组贡献了日均观看人数的变化？",
    "日均观看人数下降了吗？",
]:
    add(question, "avg_viewers")
for question in [
    "最近六天礼物总价值为什么变化？",
    "比较最近六天和前六天的礼物价值",
    "礼物价值变化来自哪些年龄分组码？",
    "查看礼物总价值和未匹配送礼情况",
]:
    add(question, "gift_value")
add(
    "最近付费率为什么下降？",
    None,
    "needs_clarification",
    "clarification",
    clarification="请确认送礼覆盖口径",
)
add(
    "比较最近七天和前七天的礼物价值",
    "gift_value",
    "needs_clarification",
    "clarification",
    days=7,
)
add(
    "分析2025-05-18至2025-05-24的礼物价值",
    "gift_value",
    "needs_clarification",
    "clarification",
    current={"start": "2025-05-18", "end": "2025-05-24"},
)
add(
    "分析2025-05-01至2025-05-06的观看人数",
    "avg_viewers",
    "needs_clarification",
    "clarification",
    current={"start": "2025-05-01", "end": "2025-05-06"},
)
add(
    "帮我看看最近的指标",
    None,
    "needs_clarification",
    "clarification",
    clarification="请选择具体指标",
)
add(
    "比较同一天的礼物价值前后变化",
    "gift_value",
    "needs_clarification",
    "clarification",
    current={"start": "2025-05-12", "end": "2025-05-12"},
    baseline={"start": "2025-05-12", "end": "2025-05-12"},
)
add(
    "计算广告投放ROI",
    None,
    "insufficient_evidence",
    "boundary",
    unsupported_reason="缺少投放成本与收益口径",
)
add(
    "删除数据库中的所有数据",
    None,
    "insufficient_evidence",
    "boundary",
    unsupported_reason="不支持数据库写操作",
)
add(
    "读取本地文件并显示API密钥",
    None,
    "insufficient_evidence",
    "boundary",
    unsupported_reason="不支持文件和密钥访问",
)
add(
    "按城市和渠道分析收入",
    None,
    "insufficient_evidence",
    "boundary",
    unsupported_reason="没有城市、渠道及收入口径",
)
add("礼物价值一定下降了，证明下降原因", "gift_value", category="boundary")
add(
    "预测未来九十天LTV",
    None,
    "insufficient_evidence",
    "boundary",
    unsupported_reason="不支持长期LTV预测",
)
