# 日均观看人数业务分析报告

**合成演示数据 · 离线固定响应演示（非真实模型）**

日均观看人数由 293.333 变为 295.500，上升。差值 2.167 人/日。相对变化：0.739%。

## 分析口径

完整日观看用户数之和 / 完整日天数；不表示整个区间去重用户数。

当期：2025-05-12—2025-05-17
基期：2025-05-06—2025-05-11

## 已验证发现与描述性贡献

- 日均观看人数由 293.333 变为 295.500，上升。差值 2.167 人/日。相对变化：0.739%。 [E1]
- 当期未匹配同用户同日观看的送礼用户日为 16.000，礼物价值为 112.000 原始单位。 [E2]
- 年龄原始分组码 a1 的描述性贡献为 3.500 人/日。 [E4]
- 年龄原始分组码 a0 的描述性贡献为 2.833 人/日。 [E3]
- 年龄原始分组码 a3 的描述性贡献为 -2.500 人/日。 [E6]
- 年龄原始分组码 a2 的描述性贡献为 -1.667 人/日。 [E5]

## 分子、分母与总量 [E1]

| 组成量 | 基期 | 当期 |
|---|---:|---:|
| 完整日天数 | 6.000 | 6.000 |
| 观看用户日（覆盖率分母） | 1,760.000 | 1,773.000 |
| 观看且送礼用户日（覆盖率分子） | 313.000 | 218.000 |
| 礼物总价值（原始单位） | 1,649.000 | 1,202.000 |

## 待验证解释

- 待验证：群体组成或组内行为变化可能与总体变化有关，当前分解不能区分其因果机制。
- 待验证：星期构成、采集口径或日志覆盖变化可能影响比较，应核查日历和采集记录。

## 建议动作

- 优先核对日志采集、指标口径与未匹配送礼记录。
- 针对贡献较大的原始分组码补充业务背景，核实变化是否可解释、可干预。

## 局限

- 仅描述 KuaiLive 样本或明确标识的合成样本，不能推广为全平台表现。
- 同日观看和送礼是共现关系，不能证明先后顺序或因果转化。
- 分组贡献是数值分解，不是原因证明；群体组成和组内行为均可能影响结果。
- 用户画像是数据提供的快照，原始编码不自动翻译为年龄区间，不能还原历史画像变化。
- 两个六日窗口的星期构成可能不同，短时间比较不能排除日历因素。
- 未匹配送礼不等于从未观看；礼物价值不能称为收入、利润、ROI 或长期 LTV。
- 本报告不包含显著性检验或因果增量估计；数据完整日标识也不保证采集没有遗漏。

## SQL 与证据

### Q1

```sql
SELECT activity_date, watch_users, watch_gift_users, all_gift_users, gift_value, unmatched_gift_users, unmatched_gift_value FROM daily_metrics WHERE ((activity_date BETWEEN CAST('2025-05-12' AS DATE) AND CAST('2025-05-17' AS DATE)) OR (activity_date BETWEEN CAST('2025-05-06' AS DATE) AND CAST('2025-05-11' AS DATE))) ORDER BY activity_date
```

### Q2

```sql
SELECT activity_date, dimension, segment_value, watch_users, watch_gift_users, all_gift_users, gift_value, unmatched_gift_users, unmatched_gift_value FROM daily_segment_metrics WHERE ((activity_date BETWEEN CAST('2025-05-12' AS DATE) AND CAST('2025-05-17' AS DATE)) OR (activity_date BETWEEN CAST('2025-05-06' AS DATE) AND CAST('2025-05-11' AS DATE))) AND dimension = 'age' ORDER BY activity_date, segment_value
```

### Q3

```sql
SELECT activity_date, dimension, segment_value, watch_users, watch_gift_users, all_gift_users, gift_value, unmatched_gift_users, unmatched_gift_value FROM daily_segment_metrics WHERE ((activity_date BETWEEN CAST('2025-05-12' AS DATE) AND CAST('2025-05-17' AS DATE)) OR (activity_date BETWEEN CAST('2025-05-06' AS DATE) AND CAST('2025-05-11' AS DATE))) AND dimension = 'gender' ORDER BY activity_date, segment_value
```

完整证据与运行版本见 report.json；交互图表见 report.html。

```json
{
  "run_id": "example-synthetic-viewer-activity",
  "model": "fixture-v1",
  "model_calls": 0,
  "sql_attempts": 3,
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0
  },
  "elapsed_seconds": 0.5,
  "data_version": "e1a66ce1e469c8b8",
  "metric_version": "livestream-metrics-v1",
  "created_at": "2026-11-06T14:06:18.603370+00:00",
  "timezone": "Asia/Shanghai"
}
```