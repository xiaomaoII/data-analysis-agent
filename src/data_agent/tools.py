"""The model can request only these reviewed analysis capabilities."""

from data_agent.analysis import compare, contributions
from data_agent.database.query import execute

TOOL_CATALOG = {
    "query_daily_metrics": "校验并查询确认窗口的每日指标组成量",
    "compare_periods": "计算用户日加权比率、日均人数或总价值及变化",
    "group_contributions": "按年龄或性别原始码计算可加总的描述性贡献",
}


class AnalysisTools:
    def __init__(self, settings):
        self.settings = settings

    def query_daily_metrics(self, *args, **kwargs):
        return execute(self.settings, *args, **kwargs)

    @staticmethod
    def compare_periods(task, query):
        return compare(task, query)

    @staticmethod
    def group_contributions(task, overall, query, start_id):
        return contributions(task, overall, query, start_id)
