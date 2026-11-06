import hashlib
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from data_agent.semantic import COMPONENTS, METRIC_VERSION

START, END = date(2025, 5, 5), date(2025, 5, 17)


def _sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _validate_table_shapes(con):
    """Check the fixed mart grains before publishing a prepared database."""
    users = con.execute("SELECT count(*) FROM source_user").fetchone()[0]
    days = con.execute(
        "SELECT count(*) FROM dataset_days WHERE is_complete"
    ).fetchone()[0]
    groups = con.execute(
        "SELECT count(DISTINCT COALESCE(age,'unknown')::VARCHAR) + "
        "count(DISTINCT COALESCE(gender,'unknown')::VARCHAR) FROM source_user"
    ).fetchone()[0]
    contracts = {
        "user_daily": (["user_id", "activity_date"], users * days),
        "daily_metrics": (["activity_date"], days),
        "daily_segment_metrics": (
            ["activity_date", "dimension", "segment_value"],
            groups * days,
        ),
    }
    checks = {}
    for table, (keys, expected) in contracts.items():
        actual = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        null_keys = con.execute(
            f"SELECT count(*) FROM {table} WHERE "
            + " OR ".join(f"{key} IS NULL" for key in keys)
        ).fetchone()[0]
        duplicates = con.execute(
            f"SELECT count(*) FROM (SELECT {','.join(keys)} FROM {table} "
            f"GROUP BY {','.join(keys)} HAVING count(*)>1)"
        ).fetchone()[0]
        checks[table] = {
            "key": keys,
            "expected_rows": expected,
            "actual_rows": actual,
            "null_key_rows": null_keys,
            "duplicate_keys": duplicates,
        }
        if actual != expected or null_keys or duplicates:
            raise ValueError(
                f"{table} 粒度校验失败：预期 {expected} 行，实际 {actual} 行，"
                f"空键 {null_keys} 行，重复键 {duplicates} 组"
            )
    return checks


def synthetic_inputs(scenario="change", seed=20261013):
    if scenario not in {
        "change",
        "flat",
        "zero",
        "missing",
        "increase",
        "baseline_zero",
    }:
        raise ValueError("未知合成情景")
    rng = np.random.default_rng(seed)
    users = pd.DataFrame(
        {
            "user_id": range(1, 401),
            "age": [f"a{i % 4}" for i in range(400)],
            "gender": [f"g{i % 2}" for i in range(400)],
        }
    )
    watch, gifts = [], []
    for offset in range(13):
        day = START + timedelta(days=offset)
        if scenario == "missing" and offset == 8:
            continue
        stamp = int(
            datetime(day.year, day.month, day.day, 4, tzinfo=timezone.utc).timestamp()
            * 1000
        )
        for user in range(1, 401):
            active = user <= 300 if scenario == "flat" else rng.random() < 0.75
            if scenario == "zero":
                active = False
            if active:
                watch.append((user, stamp, 60000))
                if user % 5 == 0:  # duplicate events exercise aggregate-before-join
                    watch.append((user, stamp + 1000, 30000))
            prob = 0.18 if offset < 7 else (0.05 if user % 4 == 0 else 0.14)
            if scenario == "increase" and offset >= 7:
                prob = 0.35
            gifted = active and (
                user % 10 == 0 if scenario == "flat" else rng.random() < prob
            )
            if scenario == "baseline_zero" and offset < 7:
                gifted = False
            if gifted:
                gifts.extend([(user, stamp + 3000, 3), (user, stamp + 4000, 2)])
            elif (
                not active
                and scenario not in {"zero", "flat", "baseline_zero"}
                and user % 41 == 0
            ):
                gifts.append((user, stamp + 5000, 7))
    return (
        users,
        pd.DataFrame(watch, columns=["user_id", "timestamp", "watch_live_time"]),
        pd.DataFrame(gifts, columns=["user_id", "timestamp", "gift_price"]),
    )


def prepare(settings, dataset_id="synthetic", source=None, scenario="change"):
    """Build a temporary database; publish only after all reconciliation checks pass."""
    settings.initialize()
    target = settings.database(dataset_id)
    temporary = target.with_name(target.name + f".{uuid.uuid4().hex}.partial")
    con = duckdb.connect(str(temporary))
    try:
        con.execute("SET TimeZone='Asia/Shanghai'")
        con.execute("SET threads=2")
        provenance = {}
        if dataset_id == "synthetic":
            users, watches, gifts = synthetic_inputs(scenario)
            for name, frame in [
                ("source_user", users),
                ("source_watch", watches),
                ("source_gift", gifts),
            ]:
                con.register(name, frame)
            provenance = {"type": "synthetic", "seed": 20261013, "scenario": scenario}
        else:
            if source is None:
                raise ValueError("真实数据导入需要 --source 项目二目录")
            source = Path(source).resolve()
            cfg = json.loads((source / "config.json").read_text(encoding="utf-8-sig"))
            if (
                cfg.get("timezone") != "Asia/Shanghai"
                or cfg.get("test_status") != "locked_not_evaluated"
            ):
                raise ValueError("源数据配置或测试锁状态与本版合同不一致")
            for logical, name in [
                ("source_user", "user"),
                ("source_watch", "click"),
                ("source_gift", "gift"),
            ]:
                path = source / "data" / "parquet" / f"{name}.parquet"
                receipt = json.loads(
                    path.with_suffix(".json").read_text(encoding="utf-8")
                )
                digest = _sha(path)
                if digest != receipt["parquet_sha256"]:
                    raise ValueError(f"{name} 源文件校验失败")
                provenance[name] = {"path": str(path), "sha256": digest}
                con.read_parquet(str(path)).create_view(logical)
        if con.execute(
            "SELECT count(*)-count(DISTINCT user_id) FROM source_user"
        ).fetchone()[0]:
            raise ValueError("用户维表主键不唯一")
        # An undated event cannot safely be assigned to the permitted window.
        timestamp_nulls = {
            table: con.execute(
                f"SELECT count(*) FROM {table} WHERE timestamp IS NULL"
            ).fetchone()[0]
            for table in ["source_watch", "source_gift"]
        }
        if any(timestamp_nulls.values()):
            raise ValueError(
                "事件时间戳缺失，无法判定允许日期范围："
                f"观看 {timestamp_nulls['source_watch']} 条，"
                f"送礼 {timestamp_nulls['source_gift']} 条；未发布新库"
            )
        # Timestamp filtering occurs before aggregation; locked-period events never enter the mart.
        start_ms = int(datetime(2025, 5, 4, 16, tzinfo=timezone.utc).timestamp() * 1000)
        end_ms = int(datetime(2025, 5, 17, 16, tzinfo=timezone.utc).timestamp() * 1000)
        con.execute(
            "CREATE TEMP TABLE w AS SELECT user_id, CAST(to_timestamp(timestamp/1000.0) AS DATE) AS activity_date, count(*) AS watch_count FROM source_watch WHERE timestamp>=? AND timestamp<? GROUP BY 1,2",
            [start_ms, end_ms],
        )
        con.execute(
            "CREATE TEMP TABLE g AS SELECT user_id, CAST(to_timestamp(timestamp/1000.0) AS DATE) AS activity_date, count(*) AS gift_count, sum(gift_price)::DOUBLE AS gift_value FROM source_gift WHERE timestamp>=? AND timestamp<? GROUP BY 1,2",
            [start_ms, end_ms],
        )
        unknown = con.execute(
            "SELECT count(*) FROM (SELECT user_id FROM w UNION SELECT user_id FROM g) e ANTI JOIN source_user u USING(user_id)"
        ).fetchone()[0]
        if unknown:
            raise ValueError("事件包含维表中不存在的用户")
        if con.execute(
            "SELECT count(*) FROM source_gift WHERE timestamp>=? AND timestamp<? AND (gift_price IS NULL OR gift_price<0)",
            [start_ms, end_ms],
        ).fetchone()[0]:
            raise ValueError("礼物价值存在未知或负值")
        con.execute(
            "CREATE TABLE dataset_days AS SELECT CAST(d AS DATE) activity_date, TRUE AS is_complete FROM generate_series(DATE '2025-05-05', DATE '2025-05-17', INTERVAL 1 DAY) t(d)"
        )
        if dataset_id == "synthetic" and scenario == "missing":
            con.execute(
                "UPDATE dataset_days SET is_complete=FALSE WHERE activity_date=DATE '2025-05-13'"
            )
        con.execute("""CREATE TABLE user_daily AS
          SELECT u.user_id, d.activity_date, COALESCE(u.age,'unknown')::VARCHAR AS age,
          COALESCE(u.gender,'unknown')::VARCHAR AS gender,
          COALESCE(w.watch_count,0)::BIGINT AS watch_count, COALESCE(g.gift_count,0)::BIGINT AS gift_count,
          COALESCE(g.gift_value,0)::DOUBLE AS gift_value
          FROM source_user u CROSS JOIN dataset_days d
          LEFT JOIN w ON u.user_id=w.user_id AND d.activity_date=w.activity_date
          LEFT JOIN g ON u.user_id=g.user_id AND d.activity_date=g.activity_date
          WHERE d.is_complete""")
        aggregates = """sum((watch_count>0)::INT)::BIGINT watch_users,
          sum((watch_count>0 AND gift_count>0)::INT)::BIGINT watch_gift_users,
          sum((gift_count>0)::INT)::BIGINT all_gift_users, sum(gift_value)::DOUBLE gift_value,
          sum((watch_count=0 AND gift_count>0)::INT)::BIGINT unmatched_gift_users,
          sum(CASE WHEN watch_count=0 THEN gift_value ELSE 0 END)::DOUBLE unmatched_gift_value"""
        con.execute(
            f"CREATE TABLE daily_metrics AS SELECT activity_date, {aggregates} FROM user_daily GROUP BY 1"
        )
        con.execute(
            f"CREATE TABLE daily_segment_metrics AS SELECT activity_date,'age' AS dimension,age AS segment_value,{aggregates} FROM user_daily GROUP BY 1,3 UNION ALL SELECT activity_date,'gender',gender,{aggregates} FROM user_daily GROUP BY 1,3"
        )
        checks = {
            "timestamp_nulls": timestamp_nulls,
            "table_shapes": _validate_table_shapes(con),
            "duplicate_user_days": con.execute(
                "SELECT count(*) FROM (SELECT user_id,activity_date FROM user_daily GROUP BY 1,2 HAVING count(*)<>1)"
            ).fetchone()[0],
            "gift_value_raw": con.execute(
                "SELECT coalesce(sum(gift_value),0) FROM g"
            ).fetchone()[0],
            "gift_value_mart": con.execute(
                "SELECT coalesce(sum(gift_value),0) FROM user_daily"
            ).fetchone()[0],
            "watch_events_raw": con.execute(
                "SELECT coalesce(sum(watch_count),0) FROM w"
            ).fetchone()[0],
            "watch_events_mart": con.execute(
                "SELECT coalesce(sum(watch_count),0) FROM user_daily"
            ).fetchone()[0],
        }
        if (
            checks["duplicate_user_days"]
            or checks["gift_value_raw"] != checks["gift_value_mart"]
            or checks["watch_events_raw"] != checks["watch_events_mart"]
        ):
            raise ValueError("聚合后对账失败")
        overall = con.execute(
            "SELECT * FROM daily_metrics ORDER BY activity_date"
        ).fetchdf()
        for dim in ["age", "gender"]:
            grouped = con.execute(
                f"SELECT activity_date,{','.join(f'sum({c}) AS {c}' for c in COMPONENTS)} FROM daily_segment_metrics WHERE dimension=? GROUP BY 1 ORDER BY 1",
                [dim],
            ).fetchdf()
            pd.testing.assert_frame_equal(overall, grouped, check_dtype=False)
        checks["segment_reconciled"] = True
        provenance_json = json.dumps(provenance, sort_keys=True)
        metadata = {
            "dataset_id": dataset_id,
            "label": "合成演示数据"
            if dataset_id == "synthetic"
            else "KuaiLive 开发期真实样本",
            "start": str(START),
            "end": str(END),
            "timezone": "Asia/Shanghai",
            "metric_version": METRIC_VERSION,
            "data_version": hashlib.sha256(
                (provenance_json + METRIC_VERSION).encode()
            ).hexdigest()[:16],
            "provenance": provenance,
            "checks": checks,
            "row_counts": {
                name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                for name in ["user_daily", "daily_metrics", "daily_segment_metrics"]
            },
            "complete_dates": [
                str(r[0])
                for r in con.execute(
                    "SELECT activity_date FROM dataset_days WHERE is_complete ORDER BY 1"
                ).fetchall()
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        con.execute("CREATE TABLE dataset_metadata (payload VARCHAR)")
        con.execute(
            "INSERT INTO dataset_metadata VALUES (?)",
            [json.dumps(metadata, ensure_ascii=False)],
        )
        con.close()
        os.replace(temporary, target)
        return metadata
    except BaseException:
        con.close()
        temporary.unlink(missing_ok=True)
        raise


def metadata(settings, dataset_id):
    path = settings.database(dataset_id)
    if not path.exists():
        raise FileNotFoundError("数据集尚未准备，请先执行 prepare 命令")
    with duckdb.connect(str(path), read_only=True) as con:
        return json.loads(
            con.execute("SELECT payload FROM dataset_metadata").fetchone()[0]
        )
