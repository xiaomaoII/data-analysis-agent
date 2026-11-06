import json
import os
import subprocess
import sys
import time

from sqlglot import exp, parse
from sqlglot.optimizer.scope import traverse_scope

from data_agent.models import AnalysisTask, QueryResult
from data_agent.semantic import COMPONENTS


def expected_columns(dimension=None):
    return (
        ["activity_date"]
        + (["dimension", "segment_value"] if dimension else [])
        + COMPONENTS
    )


def canonical_sql(task: AnalysisTask, dimension=None):
    windows = [task.current] + ([task.baseline] if task.baseline else [])
    predicate = " OR ".join(
        f"(activity_date BETWEEN DATE '{w.start}' AND DATE '{w.end}')" for w in windows
    )
    table = "daily_segment_metrics" if dimension else "daily_metrics"
    restriction = f" AND dimension = '{dimension}'" if dimension else ""
    return (
        f"SELECT {', '.join(expected_columns(dimension))} FROM {table} WHERE ({predicate}){restriction} ORDER BY activity_date"
        + (", segment_value" if dimension else "")
    )


def validate_sql(sql, task, dimension=None):
    """Strict AST allowlist. Result equality to the semantic oracle is checked in worker."""
    if len(sql) > 16000:
        raise ValueError("SQL 过长")
    expressions = parse(sql, read="duckdb")
    if len(expressions) != 1 or not isinstance(expressions[0], exp.Select):
        raise ValueError("仅支持一条 SELECT，可含非递归 CTE")
    tree = expressions[0]
    # Positive allowlist: new SQL features are denied until explicitly reviewed.
    allowed = {
        "Select",
        "From",
        "Table",
        "Identifier",
        "Column",
        "Where",
        "And",
        "Or",
        "Not",
        "Paren",
        "Between",
        "GTE",
        "LTE",
        "GT",
        "LT",
        "EQ",
        "NEQ",
        "Literal",
        "Cast",
        "DataType",
        "Order",
        "Ordered",
        "Alias",
        "TableAlias",
        "With",
        "CTE",
        "Subquery",
        "Limit",
        "Boolean",
        "Null",
        "In",
        "Distinct",
    }
    for node in tree.walk():
        if type(node).__name__ not in allowed:
            raise ValueError(f"不支持的 SQL 结构：{type(node).__name__}")
        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise ValueError("不支持递归 CTE")
    table = "daily_segment_metrics" if dimension else "daily_metrics"
    found = False
    for scope in traverse_scope(tree):
        for _, (_, source) in scope.selected_sources.items():
            if isinstance(source, exp.Table):
                if source.name != table or source.db or source.catalog:
                    raise ValueError("只允许当前任务指定的分析表")
                found = True
        for col in scope.columns:
            if col.name not in expected_columns(dimension):
                raise ValueError(f"不支持的字段：{col.name}")
    if not found:
        raise ValueError("SQL 没有引用受支持的分析表")
    if tree.named_selects != expected_columns(dimension):
        raise ValueError("输出列必须符合查询合同，且顺序一致")
    if dimension:
        eqs = list(tree.find_all(exp.EQ))
        if not any(
            isinstance(e.this, exp.Column)
            and e.this.name == "dimension"
            and isinstance(e.expression, exp.Literal)
            and e.expression.this == dimension
            for e in eqs
        ):
            raise ValueError("分组查询必须显式过滤单一指定维度")
    if not list(tree.find_all(exp.Where)):
        raise ValueError("查询必须显式过滤日期")
    return tree.sql(dialect="duckdb")


def execute(
    settings,
    dataset_id,
    task,
    sql,
    query_id,
    data_version,
    dimension=None,
    timeout=None,
):
    checked = validate_sql(sql, task, dimension)
    payload = {
        "database": str(settings.database(dataset_id)),
        "sql": checked,
        "oracle_sql": canonical_sql(task, dimension),
        "max_rows": settings.max_rows,
        "columns": expected_columns(dimension),
    }
    # The query process needs neither an API credential nor the rest of the host environment.
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper()
        in {
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "TEMP",
            "TMP",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "LANG",
        }
    }
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, "-m", "data_agent.database.worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        creationflags=creationflags,
    )
    try:
        output, error = process.communicate(
            json.dumps(payload), timeout=timeout or settings.sql_timeout
        )
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise TimeoutError("SQL 超时，查询进程已终止") from None
    if process.returncode:
        raise ValueError("查询进程失败：" + error[-500:])
    response = json.loads(output)
    if "error" in response:
        raise ValueError(response["error"])
    return QueryResult(
        query_id=query_id,
        sql=checked,
        columns=payload["columns"],
        rows=response["rows"],
        data_version=data_version,
        dimension=dimension,
        elapsed_seconds=time.monotonic() - started,
    )
