"""Compose category-owned summaries without reversing support dependencies."""
from .support.reporting import make_report as _make_report
from .agent_core.reporting import enrich_report as core_report
from .agent_story.reporting import enrich_report as story_report


def make_report(runs, output):
    return _make_report(runs, output, {"perf": core_report, "agent": story_report})
