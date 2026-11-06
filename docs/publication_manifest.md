# GitHub 发布文件清单

目标：`xiaomaoII/data-analysis-agent`，公开 MVP 源码仓库。清单核验日期：2026-11-06。

包含源码、测试、文档、依赖声明、启停脚本、固定种子合成样例、界面截图与公开验证摘要。截图为聚合指标，不含原始用户 ID。所有合成报告明确标识数据与运行模式。

排除真实数据与真实样例、数据库、密钥、虚拟环境、IDE 设置、运行日志、临时工作区和本机测试 XML。Git 提交使用 GitHub noreply 地址。发布范围不改变项目二内容，也不代表真实模型验收已完成。

文件列表（含本清单本身）：

- `.env.example`
- `.gitignore`
- `.streamlit/config.toml`
- `AGENTS.md`
- `PROJECT_STATE.md`
- `README.md`
- `docs/architecture.md`
- `docs/data_and_publication.md`
- `docs/demo_and_learning.md`
- `docs/publication_manifest.md`
- `docs/roadmap.md`
- `pyproject.toml`
- `reports/evaluation_demo.json`
- `reports/examples/index.html`
- `reports/examples/index.json`
- `reports/examples/synthetic-gift-coverage/Q1.csv`
- `reports/examples/synthetic-gift-coverage/Q2.csv`
- `reports/examples/synthetic-gift-coverage/Q3.csv`
- `reports/examples/synthetic-gift-coverage/evidence.json`
- `reports/examples/synthetic-gift-coverage/report.html`
- `reports/examples/synthetic-gift-coverage/report.json`
- `reports/examples/synthetic-gift-coverage/report.md`
- `reports/examples/synthetic-gift-value/Q1.csv`
- `reports/examples/synthetic-gift-value/Q2.csv`
- `reports/examples/synthetic-gift-value/Q3.csv`
- `reports/examples/synthetic-gift-value/evidence.json`
- `reports/examples/synthetic-gift-value/report.html`
- `reports/examples/synthetic-gift-value/report.json`
- `reports/examples/synthetic-gift-value/report.md`
- `reports/examples/synthetic-viewer-activity/Q1.csv`
- `reports/examples/synthetic-viewer-activity/Q2.csv`
- `reports/examples/synthetic-viewer-activity/Q3.csv`
- `reports/examples/synthetic-viewer-activity/evidence.json`
- `reports/examples/synthetic-viewer-activity/report.html`
- `reports/examples/synthetic-viewer-activity/report.json`
- `reports/examples/synthetic-viewer-activity/report.md`
- `reports/public_validation.json`
- `reports/ui-preview.jpg`
- `requirements-lock.txt`
- `scripts/create_examples.py`
- `scripts/package_source.py`
- `scripts/verify_real_data.py`
- `src/data_agent/__init__.py`
- `src/data_agent/analysis.py`
- `src/data_agent/api.py`
- `src/data_agent/cli.py`
- `src/data_agent/config.py`
- `src/data_agent/database/__init__.py`
- `src/data_agent/database/prepare.py`
- `src/data_agent/database/query.py`
- `src/data_agent/database/worker.py`
- `src/data_agent/evaluation/__init__.py`
- `src/data_agent/evaluation/cases.py`
- `src/data_agent/evaluation/runner.py`
- `src/data_agent/extensions.py`
- `src/data_agent/llm.py`
- `src/data_agent/models.py`
- `src/data_agent/orchestration.py`
- `src/data_agent/reporting.py`
- `src/data_agent/semantic.py`
- `src/data_agent/store.py`
- `src/data_agent/tools.py`
- `src/data_agent/ui.py`
- `start.ps1`
- `stop.ps1`
- `tests/conftest.py`
- `tests/test_agent.py`
- `tests/test_api.py`
- `tests/test_data_and_sql.py`
- `tests/test_import_validation.py`
