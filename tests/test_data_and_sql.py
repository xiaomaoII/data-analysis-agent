import hashlib
import json
import subprocess
import sys
from dataclasses import replace

import duckdb
import pandas as pd
import pytest

from data_agent.analysis import compare, contributions
from data_agent.config import Settings
from data_agent.database.prepare import prepare, synthetic_inputs
from data_agent.database.query import canonical_sql, execute, validate_sql


def query(settings, task, dimension=None, sql=None):
    return execute(
        settings,
        "synthetic",
        task,
        sql or canonical_sql(task, dimension),
        "Q1",
        "test",
        dimension,
    )


def test_aggregate_before_join_and_independent_raw_reconciliation(settings):
    users, watch, gifts = synthetic_inputs()
    with duckdb.connect(str(settings.database("synthetic")), read_only=True) as con:
        assert con.execute("SELECT sum(watch_count) FROM user_daily").fetchone()[
            0
        ] == len(watch)
        assert con.execute("SELECT sum(gift_count) FROM user_daily").fetchone()[
            0
        ] == len(gifts)
        assert (
            con.execute("SELECT sum(gift_value) FROM user_daily").fetchone()[0]
            == gifts.gift_price.sum()
        )
        assert (
            con.execute("SELECT count(*) FROM user_daily").fetchone()[0]
            == len(users) * 13
        )
        assert con.execute(
            "SELECT min(activity_date)::VARCHAR,max(activity_date)::VARCHAR FROM user_daily"
        ).fetchone() == ("2025-05-05", "2025-05-17")
        assert (
            con.execute(
                "SELECT sum(unmatched_gift_users) FROM daily_metrics"
            ).fetchone()[0]
            > 0
        )
    # Independent pandas grouping uses event data, not mart aggregation SQL.
    watch["day"] = (
        pd.to_datetime(watch.timestamp, unit="ms", utc=True)
        .dt.tz_convert("Asia/Shanghai")
        .dt.date
    )
    gifts["day"] = (
        pd.to_datetime(gifts.timestamp, unit="ms", utc=True)
        .dt.tz_convert("Asia/Shanghai")
        .dt.date
    )
    viewers = set(
        map(tuple, watch[["user_id", "day"]].drop_duplicates().values.tolist())
    )
    gifters = set(
        map(tuple, gifts[["user_id", "day"]].drop_duplicates().values.tolist())
    )
    with duckdb.connect(str(settings.database("synthetic")), read_only=True) as con:
        assert con.execute(
            "SELECT sum(watch_gift_users) FROM daily_metrics"
        ).fetchone()[0] == len(viewers & gifters)
        assert con.execute(
            "SELECT sum(unmatched_gift_users) FROM daily_metrics"
        ).fetchone()[0] == len(gifters - viewers)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE daily_metrics",
        "SELECT 1; SELECT 2",
        "SELECT * FROM read_csv('/secret')",
        "SELECT * FROM user_daily",
        "SELECT getenv('SECRET')",
        "ATTACH 'x.duckdb' AS other",
        "COPY daily_metrics TO 'x.csv'",
        "INSTALL httpfs",
        "SELECT * FROM range(100000000000)",
        "WITH RECURSIVE x AS (SELECT 1) SELECT * FROM x",
        "SELECT * FROM daily_metrics a CROSS JOIN daily_metrics b",
    ],
)
def test_unsafe_sql_rejected(task, sql):
    with pytest.raises(ValueError):
        validate_sql(sql, task)


def test_exact_query_and_cte_allowed(settings, task):
    result = query(settings, task)
    assert len(result.rows) == 12
    sql = canonical_sql(task).replace("FROM daily_metrics", "FROM source_rows")
    result = query(
        settings,
        task,
        sql="WITH source_rows AS (SELECT activity_date,watch_users,watch_gift_users,all_gift_users,gift_value,unmatched_gift_users,unmatched_gift_value FROM daily_metrics) "
        + sql,
    )
    assert len(result.rows) == 12


def test_semantically_wrong_window_rejected(settings, task):
    with pytest.raises(ValueError, match="不一致"):
        query(
            settings, task, sql=canonical_sql(task).replace("2025-05-12", "2025-05-13")
        )


def test_missing_dimension_filter_rejected(settings, task):
    sql = canonical_sql(task, "age").replace(" AND dimension = 'age'", "")
    with pytest.raises(ValueError, match="维度"):
        query(settings, task, "age", sql)


def test_wrong_dimension_or_filter_rejected(settings, task):
    sql = canonical_sql(task, "age").replace(
        "dimension = 'age'", "(dimension = 'age' OR dimension = 'gender')"
    )
    with pytest.raises(ValueError):
        query(settings, task, "age", sql)


def test_no_truncation_and_timeout(settings, task):
    with pytest.raises(ValueError, match="上限"):
        query(replace(settings, max_rows=2), task)
    with pytest.raises(TimeoutError):
        execute(
            settings,
            "synthetic",
            task,
            canonical_sql(task),
            "Q1",
            "test",
            timeout=0.00001,
        )


@pytest.mark.parametrize("metric", ["gift_coverage", "avg_viewers", "gift_value"])
def test_contributions_reconcile_and_ratio_is_weighted(settings, task, metric):
    task = task.model_copy(update={"metric": metric})
    overall = query(settings, task)
    evidence = compare(task, overall)
    values = evidence[0].values
    if metric == "gift_coverage":
        assert (
            values["current"]
            == values["current_components"]["watch_gift_users"]
            / values["current_components"]["watch_users"]
        )
    for dim in ["age", "gender"]:
        groups = contributions(task, evidence[0], query(settings, task, dim), 3)
        assert sum(e.values["contribution"] for e in groups) == pytest.approx(
            values["delta"] * (100 if metric == "gift_coverage" else 1)
        )


def test_failed_import_preserves_last_database(tmp_path):
    settings = Settings(root=tmp_path)
    prepare(settings, "synthetic")
    before = hashlib.sha256(settings.database("synthetic").read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        prepare(settings, "synthetic", scenario="invalid")
    assert (
        hashlib.sha256(settings.database("synthetic").read_bytes()).hexdigest()
        == before
    )


def test_query_worker_disables_external_access(settings):
    payload = {
        "database": str(settings.database("synthetic")),
        "sql": "SELECT * FROM read_text('anything')",
        "oracle_sql": "SELECT 1",
        "columns": ["x"],
        "max_rows": 10,
    }
    result = subprocess.run(
        [sys.executable, "-m", "data_agent.database.worker"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert "error" in json.loads(result.stdout)


def test_real_import_timestamp_boundaries_and_source_unchanged(tmp_path):
    from datetime import datetime, timezone

    source = tmp_path / "source"
    parquet = source / "data" / "parquet"
    parquet.mkdir(parents=True)
    config = {"timezone": "Asia/Shanghai", "test_status": "locked_not_evaluated"}
    (source / "config.json").write_text(json.dumps(config))
    lo = int(datetime(2025, 5, 4, 16, tzinfo=timezone.utc).timestamp() * 1000)
    hi = int(datetime(2025, 5, 17, 16, tzinfo=timezone.utc).timestamp() * 1000)
    frames = {
        "user": pd.DataFrame({"user_id": [1], "age": ["a"], "gender": ["g"]}),
        "click": pd.DataFrame(
            {
                "user_id": [1] * 4,
                "timestamp": [lo - 1, lo, hi - 1, hi],
                "watch_live_time": [1000] * 4,
            }
        ),
        "gift": pd.DataFrame(
            {
                "user_id": [1] * 4,
                "timestamp": [lo - 1, lo, hi - 1, hi],
                "gift_price": [999, 2, 3, 999],
            }
        ),
    }
    receipts = {}
    for name, frame in frames.items():
        path = parquet / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_suffix(".json").write_text(json.dumps({"parquet_sha256": digest}))
        receipts[name] = digest
    settings = Settings(root=tmp_path / "target")
    result = prepare(settings, "kuailive_dev", source)
    assert result["checks"]["gift_value_mart"] == 5
    assert result["checks"]["watch_events_mart"] == 2
    assert json.loads((source / "config.json").read_text()) == config
    for name, digest in receipts.items():
        assert (
            hashlib.sha256((parquet / f"{name}.parquet").read_bytes()).hexdigest()
            == digest
        )
