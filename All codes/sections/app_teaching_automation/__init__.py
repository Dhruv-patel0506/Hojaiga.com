"""Section 1 - application teaching + automation: understand / teach / delegate through ONE engine (core_organs.app_teaching_automation)."""
from core_organs.app_teaching_automation import AppIntelligenceEngine, AppTeachingAutomationSection  # noqa: F401


def section(**kw):
    return AppTeachingAutomationSection(**kw)
