METRIC_VERSION = "livestream-metrics-v1"
METRICS = {
    "gift_coverage": {
        "name": "观看用户送礼覆盖率",
        "unit": "%",
        "definition": "同日观看且送礼的用户日数 / 观看用户日数；多日按分子分母分别加总，不是区间去重用户转化率。",
    },
    "avg_viewers": {
        "name": "日均观看人数",
        "unit": "人/日",
        "definition": "完整日观看用户数之和 / 完整日天数；不表示整个区间去重用户数。",
    },
    "gift_value": {
        "name": "礼物总价值",
        "unit": "原始礼物价值单位",
        "definition": "所选日期 gift_price 的合计，包含未匹配同用户同日观看的送礼记录；不等于收入或利润。",
    },
}
COMPONENTS = [
    "watch_users",
    "watch_gift_users",
    "all_gift_users",
    "gift_value",
    "unmatched_gift_users",
    "unmatched_gift_value",
]
DIMENSIONS = {"age": "年龄原始分组码", "gender": "性别原始分组码"}
LIMITATIONS = [
    "仅描述 KuaiLive 样本或明确标识的合成样本，不能推广为全平台表现。",
    "同日观看和送礼是共现关系，不能证明先后顺序或因果转化。",
    "分组贡献是数值分解，不是原因证明；群体组成和组内行为均可能影响结果。",
    "用户画像是数据提供的快照，原始编码不自动翻译为年龄区间，不能还原历史画像变化。",
    "两个六日窗口的星期构成可能不同，短时间比较不能排除日历因素。",
    "未匹配送礼不等于从未观看；礼物价值不能称为收入、利润、ROI 或长期 LTV。",
    "本报告不包含显著性检验或因果增量估计；数据完整日标识也不保证采集没有遗漏。",
]
HYPOTHESES = {
    "composition_or_within_group": "待验证：群体组成或组内行为变化可能与总体变化有关，当前分解不能区分其因果机制。",
    "calendar_or_collection": "待验证：星期构成、采集口径或日志覆盖变化可能影响比较，应核查日历和采集记录。",
    "gift_concentration_unknown": "待验证：礼物价值可能受少数高价值记录影响，本版未完成用户集中度诊断。",
}
ACTIONS = {
    "check_collection": "优先核对日志采集、指标口径与未匹配送礼记录。",
    "review_group_context": "针对贡献较大的原始分组码补充业务背景，核实变化是否可解释、可干预。",
    "design_controlled_test": "若形成具体干预假设，再设计有对照的实验；现有描述分析不能证明策略有效。",
}
