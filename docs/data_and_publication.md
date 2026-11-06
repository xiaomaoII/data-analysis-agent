# 数据与发布范围

## 公开仓库包含什么

源码、测试、说明文档、依赖锁定文件、Windows 启停脚本、无密钥配置示例、固定种子合成数据生成器、合成样例报告及离线验证记录。页面截图仅包含聚合指标，不包含原始用户 ID。

不包含 `.env`、`.venv`、`.idea`、原始事件、DuckDB 数据库、SQLite 运行历史、临时日志、本机备份和真实数据样例目录。历史本机验收记录中提到的真实对账文件与测试 XML 未必在公开仓库中；公开验证以 `reports/public_validation.json` 为准。

## 可复现的公开演示

按 README 安装 Python 3.12 环境后运行：

```powershell
.\.venv\Scripts\python.exe -m data_agent.cli prepare --dataset synthetic
.\.venv\Scripts\python.exe scripts/create_examples.py
.\.venv\Scripts\python.exe -m data_agent.cli evaluate --mode demo
```

以上过程不调用真实模型。示例脚本默认只生成合成样例；`--dataset kuailive_dev` 仅用于已具备真实分析库的本机运行，其成果不纳入公开仓库。

## KuaiLive 适配器

真实导入面向项目二约定的目录结构：`config.json`、`data/parquet` 中的 user/click/gift 文件及 SHA256 收据；它不是通用 CSV 上传接口。数据获取、使用与再分发需遵循原始提供方的条件；本仓库不授予第三方数据的使用或再分发权。

项目三独立分析窗口限定为北京时间 2025-05-05—17，不因其他项目进度改变。代码中保留日期保护，不在公开发布中触碰项目二数据或学习文件。

## 验收记录的含义

工程测试通过、固定响应案例通过、真实模型验收是三个不同层次。公开演示验证的是流程、指标和约束，不能据此报告真实模型准确率。个人代码理解与独立实现能力另行学习和验收。
