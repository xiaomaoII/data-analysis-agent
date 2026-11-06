"""Streamlit is a client of the same API used by external callers."""

import os
from datetime import date

import httpx
import streamlit as st

from data_agent.evaluation.cases import CASES
from data_agent.models import BusinessReport
from data_agent.reporting import figures
from data_agent.semantic import METRICS

st.set_page_config(
    page_title="Data Analyst · 业务分析工作台", page_icon="📊", layout="wide"
)
API = os.getenv("DATA_AGENT_API_URL", "http://127.0.0.1:8000").rstrip("/")


def api(method, path, **kwargs):
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.request(method, API + path, **kwargs)
    if response.is_error:
        raise RuntimeError(
            response.json().get("detail", f"HTTP {response.status_code}")
        )
    return response.json()


st.caption("DATA ANALYST / 直播业务分析")
st.title("从业务问题，到可核验的发现")
st.markdown("理解指标、查询数据、分析变化，并保留每条结论的证据。")
try:
    health = api("GET", "/health")
    datasets = api("GET", "/v1/datasets")
except Exception:
    st.info("分析服务尚未连接。请使用项目的 start.ps1 启动页面和分析服务。")
    st.stop()
if not datasets:
    st.info("还没有数据集。请先运行 README 中的数据准备命令。")
    st.stop()
with st.sidebar:
    st.header("分析设置")
    ids = [d["dataset_id"] for d in datasets]
    labels = {d["dataset_id"]: d["label"] for d in datasets}
    selected = st.selectbox("数据集", ids, format_func=labels.get)
    mode = st.radio(
        "运行模式",
        ["demo", "live"],
        format_func=lambda x: (
            "离线固定响应演示" if x == "demo" else "DeepSeek 真实模型"
        ),
    )
    meta = next(d for d in datasets if d["dataset_id"] == selected)
    st.caption(
        f"可用范围：{meta['start']} — {meta['end']}\n\n时区：北京时间；原始分组码保留。"
    )
    if mode == "demo":
        st.info("使用固定响应演示流程，不调用真实模型。")
    elif not health["live_model_configured"]:
        st.warning("尚未配置模型密钥；真实模型功能待验收。")
    st.caption("数据版本：" + meta["data_version"])

examples = [CASES[i]["question"] for i in [0, 4, 8, 12, 13, 22]]
example = st.selectbox("示例问题", examples)
question = st.text_area(
    "你想了解什么？",
    value=example,
    height=100,
    key="question_" + str(examples.index(example)),
)
with st.expander("查看支持的指标口径"):
    for metric in METRICS.values():
        st.markdown(f"**{metric['name']}**：{metric['definition']}")
if st.button(
    "开始分析",
    type="primary",
    disabled=mode == "live" and not health["live_model_configured"],
):
    try:
        response = api(
            "POST",
            "/v1/analyses",
            json={"question": question, "dataset_id": selected, "mode": mode},
        )
        st.session_state["run_id"] = response["run_id"]
        st.query_params["run"] = response["run_id"]
    except Exception as exc:
        st.error(str(exc))

run_id = st.session_state.get("run_id") or st.query_params.get("run")
if run_id:

    @st.fragment(run_every="2s")
    def show_run():
        try:
            run = api("GET", f"/v1/analyses/{run_id}")
        except Exception as exc:
            st.error(str(exc))
            return
        states = {
            "queued": "正在排队",
            "running": "正在分析",
            "needs_clarification": "需要明确口径或日期",
            "completed": "分析完成",
            "insufficient_evidence": "证据不足",
            "failed": "本次分析未完成",
        }
        st.subheader(states[run["status"]])
        st.caption(
            f"任务 {run_id} · {labels.get(run['request']['dataset_id'], run['request']['dataset_id'])} · {'离线演示' if run['request']['mode'] == 'demo' else '真实模型'}"
        )
        if run.get("task"):
            task = run["task"]
            st.write(
                f"指标：{METRICS[task['metric']]['name']}；当期：{task['current']['start']}—{task['current']['end']}"
            )
            if task.get("baseline"):
                st.caption(
                    f"比较基期：{task['baseline']['start']}—{task['baseline']['end']}（日期两端均包含）"
                )
        if run["status"] == "needs_clarification":
            clarification = run["clarification"]
            st.info(clarification["reason"])
            with st.form("clarification_" + run_id):
                metric = st.selectbox(
                    "确认指标", list(METRICS), format_func=lambda x: METRICS[x]["name"]
                )
                c1, c2 = st.columns(2)
                cur = c1.date_input(
                    "当期（包含两端）",
                    value=(
                        date.fromisoformat(clarification["suggested_current"]["start"]),
                        date.fromisoformat(clarification["suggested_current"]["end"]),
                    ),
                )
                base = c2.date_input(
                    "基期（包含两端）",
                    value=(
                        date.fromisoformat(
                            clarification["suggested_baseline"]["start"]
                        ),
                        date.fromisoformat(clarification["suggested_baseline"]["end"]),
                    ),
                )
                trend = st.checkbox("仅看当期趋势")
                if st.form_submit_button("确认并继续"):
                    if len(cur) != 2 or (not trend and len(base) != 2):
                        st.error("请选择完整日期范围")
                    else:
                        payload = {
                            "metric": metric,
                            "current": {"start": str(cur[0]), "end": str(cur[1])},
                            "trend_only": trend,
                        }
                        if not trend:
                            payload["baseline"] = {
                                "start": str(base[0]),
                                "end": str(base[1]),
                            }
                        api(
                            "POST",
                            f"/v1/analyses/{run_id}/clarifications",
                            json=payload,
                        )
                        st.rerun()
        if run.get("error"):
            st.warning(run["error"])
        if run.get("report") and run["status"] == "completed":
            report = BusinessReport.model_validate(run["report"])
            st.success(report.summary)
            values = report.evidence[0].values
            st.dataframe(
                {
                    "组成量": [
                        "完整日天数",
                        "观看用户日（覆盖率分母）",
                        "观看且送礼用户日（覆盖率分子）",
                        "礼物总价值（原始单位）",
                    ],
                    "基期": [
                        values["baseline_days"],
                        values["baseline_components"]["watch_users"],
                        values["baseline_components"]["watch_gift_users"],
                        values["baseline_components"]["gift_value"],
                    ]
                    if report.task.baseline
                    else [None] * 4,
                    "当期": [
                        values["current_days"],
                        values["current_components"]["watch_users"],
                        values["current_components"]["watch_gift_users"],
                        values["current_components"]["gift_value"],
                    ],
                },
                hide_index=True,
                width="stretch",
            )
            for chart in figures(report).values():
                st.plotly_chart(chart, width="stretch")
            for f in report.findings:
                st.write(f"{f['text']} [{', '.join(f['evidence_ids'])}]")
            left, right = st.columns(2)
            left.markdown("**待验证解释**")
            for item in report.hypotheses:
                left.write(item)
            right.markdown("**建议动作**")
            for item in report.actions:
                right.write(item)
            with st.expander("数据边界与局限", expanded=True):
                for item in report.limitations:
                    st.write(item)
        if run.get("artifacts"):
            st.markdown("**下载报告与证据**")
            for name in run["artifacts"]:
                if name in {"report.md", "report.html", "report.json", "evidence.json"}:
                    st.link_button(name, f"{API}/v1/analyses/{run_id}/artifacts/{name}")
        with st.expander("查询与执行记录"):
            for q in run.get("queries", []):
                st.code(q["sql"], language="sql")
                st.dataframe(q["rows"], width="stretch")
            st.json(run.get("trace", []))

    show_run()
