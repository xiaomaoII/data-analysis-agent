"""Short-lived process. Never imports the LLM provider or loads .env."""

import json
import sys

import duckdb


def main():
    try:
        request = json.load(sys.stdin)
        with duckdb.connect(
            request["database"],
            read_only=True,
            config={
                "enable_external_access": False,
                "autoload_known_extensions": False,
                "autoinstall_known_extensions": False,
                "threads": 2,
                "memory_limit": "512MB",
            },
        ) as con:
            con.execute("SET lock_configuration=true")
            cursor = con.execute(request["sql"])
            columns = [d[0] for d in cursor.description]
            actual = cursor.fetchmany(request["max_rows"] + 1)
            if len(actual) > request["max_rows"]:
                raise ValueError("结果超过行数上限，不执行截断分析")
            if columns != request["columns"]:
                raise ValueError("结果列不符合指标合同")
            expected = con.execute(request["oracle_sql"]).fetchmany(
                request["max_rows"] + 1
            )
            if len(expected) > request["max_rows"]:
                raise ValueError("指标完整结果超过上限")
            if sorted(actual, key=str) != sorted(expected, key=str):
                raise ValueError(
                    "查询结果与可信指标查询不一致：检查窗口、过滤和分子分母"
                )
            rows = [dict(zip(columns, row)) for row in sorted(actual, key=str)]
        print(
            json.dumps({"rows": rows}, default=str, ensure_ascii=True, allow_nan=False)
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
