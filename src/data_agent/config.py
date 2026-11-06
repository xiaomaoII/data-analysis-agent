import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    root: Path
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    max_model_calls: int = 10
    max_sql_attempts: int = 6
    model_timeout: float = 30
    sql_timeout: float = 15
    run_timeout: float = 180
    max_rows: int = 1000

    @classmethod
    def load(cls):
        root = Path(
            os.environ.get("DATA_AGENT_HOME") or Path(__file__).resolve().parents[2]
        )
        load_dotenv(root / ".env", override=False)
        return cls(
            root=root,
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip(
                "/"
            ),
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        )

    def initialize(self):
        for path in (self.root / "data", self.root / "reports" / "runs"):
            path.mkdir(parents=True, exist_ok=True)

    def database(self, dataset_id: str) -> Path:
        if dataset_id not in {"synthetic", "kuailive_dev"}:
            raise ValueError("未知数据集")
        return self.root / "data" / f"{dataset_id}.duckdb"
