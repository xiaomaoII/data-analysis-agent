import json
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from data_agent.models import AnalysisRequest
from data_agent.orchestration import Analyst


class RunStore:
    def __init__(self, settings):
        self.settings = settings
        settings.initialize()
        self.path = settings.root / "data" / "runs.sqlite"
        self.lock = threading.RLock()
        with self.connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, run_id):
        with self.connect() as con:
            row = con.execute(
                "SELECT payload FROM runs WHERE id=?", [run_id]
            ).fetchone()
        if not row:
            raise KeyError(run_id)
        return json.loads(row[0])

    def put(self, run):
        run = {**run, "updated_at": datetime.now(timezone.utc).isoformat()}
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?)",
                [run["run_id"], json.dumps(run, ensure_ascii=False, allow_nan=False)],
            )

    def interrupted(self):
        with self.connect() as con:
            rows = con.execute("SELECT payload FROM runs").fetchall()
        for row in rows:
            run = json.loads(row[0])
            if run["status"] in {"queued", "running"}:
                run.update(
                    status="failed", error="服务重启，未完成任务已中断；请重新提交。"
                )
                self.put(run)


class RunManager:
    def __init__(self, settings):
        self.settings = settings
        self.store = RunStore(settings)
        self.store.interrupted()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analyst")
        self.submit_lock = threading.Lock()

    def submit(self, request, run_id=None, previous=None):
        run_id = run_id or uuid.uuid4().hex
        self.store.put(
            {
                "run_id": run_id,
                "status": "queued",
                "request": request.model_dump(mode="json"),
                "trace": [],
                "artifacts": [],
                "previous_attempts": previous.get("previous_attempts", [])
                + [
                    {
                        "request": previous["request"],
                        "clarification": previous.get("clarification"),
                        "trace": previous.get("trace", []),
                    }
                ]
                if previous
                else [],
            }
        )
        self.executor.submit(
            self._execute, request, run_id, previous.get("budget") if previous else None
        )
        return run_id

    def _execute(self, request, run_id, previous_budget=None):
        run = self.store.get(run_id)
        run["status"] = "running"
        self.store.put(run)

        def event(item):
            run["trace"].append(item)
            if item.get("task"):
                run["task"] = item["task"]
            run["budget"] = {
                k: item[k]
                for k in ["model_calls", "sql_attempts", "usage", "elapsed_seconds"]
            }
            self.store.put(run)

        try:
            result = Analyst(
                self.settings,
                request,
                run_id,
                on_event=event,
                previous_budget=previous_budget,
            ).run()
            result["previous_attempts"] = run.get("previous_attempts", [])
            self.store.put(result)
        except Exception:
            run.update(status="failed", error="任务执行器发生错误；未生成成功报告。")
            self.store.put(run)

    def clarify(self, run_id, answer):
        with self.submit_lock:
            run = self.store.get(run_id)
            if run["status"] != "needs_clarification":
                raise ValueError("任务当前不等待澄清")
            payload = run["request"]
            payload.update(answer.model_dump(mode="json", exclude_none=True))
            request = AnalysisRequest.model_validate(payload)
            return self.submit(request, run_id, previous=run)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
