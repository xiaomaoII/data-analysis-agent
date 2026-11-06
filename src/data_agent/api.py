from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from data_agent.config import Settings
from data_agent.database.prepare import metadata
from data_agent.models import AnalysisRequest, Clarification
from data_agent.semantic import METRICS
from data_agent.store import RunManager


def create_app(settings=None):
    settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app):
        app.state.manager = RunManager(settings)
        yield
        app.state.manager.close()

    app = FastAPI(title="Data Analysis Agent", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "live_model_configured": bool(settings.api_key),
            "model": settings.model,
            "scope": "local_single_user",
            "live_validation": "requires_live_evaluation",
        }

    @app.get("/v1/datasets")
    def datasets():
        result = []
        for dataset_id in ["synthetic", "kuailive_dev"]:
            try:
                item = metadata(settings, dataset_id)
                result.append(
                    {
                        k: item[k]
                        for k in [
                            "dataset_id",
                            "label",
                            "start",
                            "end",
                            "data_version",
                            "complete_dates",
                            "metric_version",
                        ]
                    }
                )
            except FileNotFoundError:
                continue
        return result

    @app.get("/v1/metrics")
    def metrics():
        return METRICS

    @app.post("/v1/analyses", status_code=202)
    def submit(request: AnalysisRequest):
        if request.mode == "live" and not settings.api_key:
            raise HTTPException(409, "尚未配置 DeepSeek 密钥；可显式选择离线演示。")
        if not settings.database(request.dataset_id).exists():
            raise HTTPException(409, "所选数据集尚未准备")
        return {"run_id": app.state.manager.submit(request), "status": "queued"}

    def get_run(run_id):
        try:
            return app.state.manager.store.get(run_id)
        except KeyError:
            raise HTTPException(404, "找不到任务") from None

    @app.get("/v1/analyses/{run_id}")
    def status(run_id: str):
        return get_run(run_id)

    @app.post("/v1/analyses/{run_id}/clarifications", status_code=202)
    def clarify(run_id: str, answer: Clarification):
        get_run(run_id)
        try:
            return {
                "run_id": app.state.manager.clarify(run_id, answer),
                "status": "queued",
            }
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/v1/analyses/{run_id}/artifacts/{name}")
    def artifact(run_id: str, name: str):
        run = get_run(run_id)
        if (
            name not in run.get("artifacts", [])
            or "/" in name
            or "\\" in name
            or ".." in name
        ):
            raise HTTPException(404, "找不到登记的导出文件")
        path = settings.root / "reports" / "runs" / run_id / name
        if not path.is_file():
            raise HTTPException(404, "导出文件不存在")
        return FileResponse(path, filename=name)

    return app
