"""Independent pandas reconciliation; predicates exclude locked-period events."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from data_agent.config import Settings
from data_agent.database.prepare import metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    settings = Settings.load()
    source = Path(args.source) / "data" / "parquet"
    start = int(datetime(2025, 5, 4, 16, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(2025, 5, 17, 16, tzinfo=timezone.utc).timestamp() * 1000)
    filters = [("timestamp", ">=", start), ("timestamp", "<", end)]
    watch = pd.read_parquet(
        source / "click.parquet", columns=["user_id", "timestamp"], filters=filters
    )
    gift = pd.read_parquet(
        source / "gift.parquet",
        columns=["user_id", "timestamp", "gift_price"],
        filters=filters,
    )
    for frame in [watch, gift]:
        frame["activity_date"] = (
            pd.to_datetime(frame.timestamp, unit="ms", utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.date
        )
    w = watch.groupby(["activity_date", "user_id"]).size().rename("watch_events")
    g = gift.groupby(["activity_date", "user_id"]).gift_price.agg(["size", "sum"])
    joined = g.join(w, how="left")
    with duckdb.connect(str(settings.database("kuailive_dev")), read_only=True) as con:
        mart = con.execute(
            "SELECT * FROM daily_metrics ORDER BY activity_date"
        ).fetchdf()
        mart["activity_date"] = mart.activity_date.dt.date
        mart = mart.set_index("activity_date")
        assert (
            con.execute(
                "SELECT max(activity_date)::VARCHAR FROM user_daily"
            ).fetchone()[0]
            == "2025-05-17"
        )
    expected = pd.DataFrame(
        {
            "watch_users": w.groupby(level=0).size(),
            "watch_gift_users": joined[joined.watch_events.notna()]
            .groupby(level=0)
            .size(),
            "all_gift_users": g.groupby(level=0).size(),
            "gift_value": g["sum"].groupby(level=0).sum(),
            "unmatched_gift_users": joined[joined.watch_events.isna()]
            .groupby(level=0)
            .size(),
            "unmatched_gift_value": joined.loc[joined.watch_events.isna(), "sum"]
            .groupby(level=0)
            .sum(),
        }
    ).fillna(0)
    pd.testing.assert_frame_equal(mart, expected, check_dtype=False, check_names=False)
    result = {
        "passed": True,
        "method": "pandas independently aggregates timestamp-filtered raw parquet",
        "window": ["2025-05-05", "2025-05-17"],
        "days_verified": len(mart),
        "metrics_verified": list(mart.columns),
        "watch_event_count": len(watch),
        "gift_event_count": len(gift),
        "gift_value": float(gift.gift_price.sum()),
        "unmatched_gift_user_days": int(expected.unmatched_gift_users.sum()),
        "source_test_status": "locked_not_evaluated",
        "data_version": metadata(settings, "kuailive_dev")["data_version"],
    }
    (settings.root / "reports" / "real_data_reconciliation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
