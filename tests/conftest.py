import uuid
from pathlib import Path

import pytest

from data_agent.config import Settings
from data_agent.database.prepare import prepare
from data_agent.models import AnalysisTask, Window


def pytest_configure(config):
    if not config.option.basetemp:
        parent = Path(__file__).resolve().parents[1] / "work"
        parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(parent / ("pytest-" + uuid.uuid4().hex[:12]))


@pytest.fixture(scope="session")
def settings(tmp_path_factory):
    value = Settings(root=tmp_path_factory.mktemp("data-agent"))
    prepare(value)
    return value


@pytest.fixture
def task():
    return AnalysisTask(
        question="最近六天观看用户的送礼覆盖率是否下降？哪些群体贡献较大？",
        metric="gift_coverage",
        current=Window(start="2025-05-12", end="2025-05-17"),
        baseline=Window(start="2025-05-06", end="2025-05-11"),
    )
