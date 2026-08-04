from datetime import datetime

from db import (
    get_dashboard_records,
    get_user_achievement_unlocks,
    unlock_user_achievements,
)
from services.prompt_builder import calculate_health_score


ACHIEVEMENTS = (
    {
        "key": "first_report_uploaded",
        "title": "First Report Uploaded",
    },
    {
        "key": "score_improved",
        "title": "Score Improved",
    },
    {
        "key": "trend_tracker",
        "title": "Trend Tracker",
    },
    {
        "key": "insights_explorer",
        "title": "Insights Explorer",
    },
)


def _report_achievement_keys(user_row, reports):
    earned = []
    if reports:
        earned.append("first_report_uploaded")
    if len(reports) >= 2:
        earned.append("trend_tracker")

        scores = [
            calculate_health_score(user_row, report)
            for report in reports
        ]
        if any(
            current > previous
            for previous, current in zip(scores, scores[1:])
        ):
            earned.append("score_improved")
    return earned


def _serialize_unlock_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%B %Y")
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).strftime("%B %Y")
    except ValueError:
        return None


def record_insights_explorer(user_id):
    unlock_user_achievements(user_id, ["insights_explorer"])


def build_achievements(user_id):
    records = get_dashboard_records(user_id)
    user_row = records["user"]
    if user_row is None:
        return None

    earned = _report_achievement_keys(
        user_row,
        records["reports"],
    )
    unlock_user_achievements(user_id, earned)
    unlocks = get_user_achievement_unlocks(user_id)

    achievements = []
    for definition in ACHIEVEMENTS:
        unlocked_at = unlocks.get(definition["key"])
        is_unlocked = unlocked_at is not None
        achievements.append({
            "title": definition["title"],
            "date": _serialize_unlock_date(unlocked_at),
            "is_unlocked": is_unlocked,
        })

    return {
        "achievements": achievements,
    }
