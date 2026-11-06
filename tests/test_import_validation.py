import hashlib
import importlib

import duckdb
import pandas as pd
import pytest

from data_agent.config import Settings
from data_agent.database.prepare import (
    _validate_table_shapes,
    prepare,
    synthetic_inputs,
)

prepare_module = importlib.import_module("data_agent.database.prepare")


@pytest.mark.parametrize("event_index", [1, 2], ids=["watch", "gift"])
def test_null_timestamp_rejects_import_and_preserves_database(
    tmp_path, monkeypatch, event_index
):
    settings = Settings(root=tmp_path)
    prepare(settings)
    before = hashlib.sha256(settings.database("synthetic").read_bytes()).hexdigest()
    frames = list(synthetic_inputs())
    frames[event_index]["timestamp"] = frames[event_index]["timestamp"].astype("Int64")
    frames[event_index].loc[0, "timestamp"] = pd.NA
    monkeypatch.setattr(prepare_module, "synthetic_inputs", lambda scenario: frames)
    with pytest.raises(ValueError, match="事件时间戳缺失") as error:
        prepare(settings)
    assert (
        "观看 1 条，送礼 0 条" if event_index == 1 else "观看 0 条，送礼 1 条"
    ) in str(error.value)
    assert (
        hashlib.sha256(settings.database("synthetic").read_bytes()).hexdigest()
        == before
    )
    assert not list(settings.database("synthetic").parent.glob("*.partial"))


@pytest.mark.parametrize("scenario,days", [("change", 13), ("missing", 12)])
def test_shape_metadata_uses_complete_dates_and_unknown_groups(
    tmp_path, monkeypatch, scenario, days
):
    original = synthetic_inputs

    def with_unknown_groups(scenario):
        users, watches, gifts = original(scenario)
        users.loc[0, ["age", "gender"]] = None
        return users, watches, gifts

    monkeypatch.setattr(prepare_module, "synthetic_inputs", with_unknown_groups)
    result = prepare(Settings(root=tmp_path), scenario=scenario)
    shapes = result["checks"]["table_shapes"]
    assert shapes["user_daily"]["actual_rows"] == 400 * days
    assert shapes["daily_metrics"]["actual_rows"] == days
    assert shapes["daily_segment_metrics"]["actual_rows"] == 8 * days
    assert all(value == 0 for value in result["checks"]["timestamp_nulls"].values())
    assert all(
        check["null_key_rows"] == check["duplicate_keys"] == 0
        for check in shapes.values()
    )


@pytest.mark.parametrize(
    "table", ["user_daily", "daily_metrics", "daily_segment_metrics"]
)
@pytest.mark.parametrize("damage", ["missing", "duplicate", "null"])
def test_shape_checks_reject_missing_duplicate_and_null_keys(tmp_path, table, damage):
    settings = Settings(root=tmp_path)
    prepare(settings)
    users, _, _ = synthetic_inputs()
    with duckdb.connect(str(settings.database("synthetic"))) as con:
        con.register("source_user", users)
        _validate_table_shapes(con)
        if damage == "missing":
            con.execute(f"DELETE FROM {table} WHERE rowid = 0")
        elif damage == "duplicate":
            # Keep the row count unchanged to test the key check independently.
            con.execute(f"DELETE FROM {table} WHERE rowid = 0")
            con.execute(f"INSERT INTO {table} SELECT * FROM {table} LIMIT 1")
        else:
            con.execute(f"UPDATE {table} SET activity_date = NULL WHERE rowid = 0")
        with pytest.raises(ValueError, match=f"{table} 粒度校验失败"):
            _validate_table_shapes(con)


def test_shape_failure_during_import_preserves_database(tmp_path, monkeypatch):
    settings = Settings(root=tmp_path)
    prepare(settings)
    before = hashlib.sha256(settings.database("synthetic").read_bytes()).hexdigest()

    def corrupt_then_validate(con):
        con.execute("DELETE FROM user_daily WHERE rowid = 0")
        return _validate_table_shapes(con)

    monkeypatch.setattr(prepare_module, "_validate_table_shapes", corrupt_then_validate)
    with pytest.raises(ValueError, match="user_daily 粒度校验失败"):
        prepare(settings)
    assert (
        hashlib.sha256(settings.database("synthetic").read_bytes()).hexdigest()
        == before
    )
    assert not list(settings.database("synthetic").parent.glob("*.partial"))
