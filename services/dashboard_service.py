from datetime import datetime, timedelta
import re

from db import get_dashboard_records
from llm import get_liver_analysis
from services.biomarker_service import (
    METRIC_LABELS,
    build_dashboard_metrics,
    report_to_dict,
)
from services.prompt_builder import calculate_health_score


TEST_SCHEDULES = {
    "lft": {
        "days": 30,
        "title": "Liver function test",
    },
    "cbc": {
        "days": 90,
        "title": "Complete blood count",
    },
    "coagulation": {
        "days": 90,
        "title": "Coagulation profile",
    },
    "afp": {
        "days": 180,
        "title": "AFP blood test",
    },
    "hepatitis": {
        "days": 365,
        "title": "Hepatitis screening",
    },
    "ultrasound": {
        "days": 365,
        "title": "Liver ultrasound review",
    },
}


def _health_status(score):
    if score >= 80:
        return "good"
    if score >= 60:
        return "fair"
    if score >= 40:
        return "needs_attention"
    return "high_risk"


def _insight_status(insight):
    lowered = insight.lower()
    monitor_words = (
        "elevated",
        "high",
        "low",
        "risk",
        "worsen",
        "abnormal",
        "monitor",
        "doctor",
        "clinician",
    )
    normal_words = (
        "normal",
        "improv",
        "stable",
        "healthy",
        "decreas",
        "recover",
    )

    if any(word in lowered for word in monitor_words):
        return "monitor"
    if any(word in lowered for word in normal_words):
        return "normal"
    return "info"


def _normalize_insight_status(status, body):
    derived_status = _insight_status(body)
    if derived_status == "monitor":
        return "monitor"

    if status is not None:
        normalized = str(status).strip().lower()
        if normalized in ("normal", "positive", "good", "stable"):
            return "normal"
        if normalized in ("monitor", "warning", "abnormal", "attention"):
            return "monitor"
        if normalized == "info":
            return "info"

    return derived_status


def _insight_title(insight, latest_metrics, index):
    lowered = insight.lower()

    for metric, label in METRIC_LABELS.items():
        metric_pattern = rf"\b{re.escape(metric.replace('_', '-'))}\b"
        label_pattern = rf"\b{re.escape(label.lower())}\b"
        if (
            re.search(metric_pattern, lowered) is None
            and re.search(label_pattern, lowered) is None
        ):
            continue

        metric_data = latest_metrics.get(metric, {})
        status = metric_data.get("status")
        trend = metric_data.get("trend")

        if status in ("normal", "negative"):
            return f"{label} in normal range"
        if trend and trend.startswith("-") and metric != "albumin":
            return f"{label} improving"
        if status in ("elevated", "low", "positive"):
            return f"{label} needs monitoring"
        return f"{label} update"

    fallback_titles = (
        "Liver health overview",
        "Biomarker update",
        "Recommended next step",
    )
    return fallback_titles[min(index, len(fallback_titles) - 1)]


def _build_ai_insights(user_id, latest_metrics):
    analysis = get_liver_analysis(user_id)

    fallback_insights = _build_fallback_insights(latest_metrics)

    if not isinstance(analysis, dict) or analysis.get("error"):
        return fallback_insights

    raw_insights = analysis.get("ai_insights", [])
    if not isinstance(raw_insights, list):
        raw_insights = []

    insights = []
    for index, item in enumerate(raw_insights[:3]):
        if isinstance(item, dict):
            body = item.get("insights") or item.get("insight") or item.get("text")
            title = item.get("insights_title") or item.get("title")
            status = item.get("insight_status") or item.get("status")
        else:
            body = item
            title = None
            status = None

        if body is None:
            continue
        body = str(body).strip()
        if not body:
            continue

        resolved_title = (
            title
            or _insight_title(body, latest_metrics, index)
        )
        insights.append({
            "insights_title": resolved_title,
            "insights": body,
            "insight_status": _normalize_insight_status(
                status,
                f"{resolved_title}. {body}",
            ),
        })

    for fallback in fallback_insights:
        if len(insights) == 3:
            break
        insights.append(fallback)

    return insights[:3]


def _build_fallback_insights(latest_metrics):
    available_metrics = [
        METRIC_LABELS[metric]
        for metric, data in latest_metrics.items()
        if data["score"] is not None
    ]
    missing_count = len(latest_metrics) - len(available_metrics)

    if available_metrics:
        coverage_text = (
            f"{len(available_metrics)} health metrics are available in your "
            "latest report history."
        )
    else:
        coverage_text = (
            "No biomarker values are available yet. Upload a liver report "
            "to establish your baseline."
        )

    if missing_count:
        next_step_text = (
            f"{missing_count} metrics do not have a recorded value yet. "
            "Upload the relevant reports for a more complete assessment."
        )
    else:
        next_step_text = (
            "All supported dashboard metrics have recorded values. "
            "Continue uploading follow-up reports to track trends."
        )

    return [
        {
            "insights_title": "Health overview",
            "insights": (
                "Your calculated health score and latest recorded metrics "
                "are available on the dashboard."
            ),
            "insight_status": "info",
        },
        {
            "insights_title": "Biomarker coverage",
            "insights": coverage_text,
            "insight_status": "info",
        },
        {
            "insights_title": "Recommended next step",
            "insights": next_step_text,
            "insight_status": "monitor" if missing_count else "normal",
        },
    ]


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value

    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _build_upcoming(uploads, now):
    due_tests = []

    for report_type, schedule in TEST_SCHEDULES.items():
        last_uploaded = _parse_datetime(uploads.get(report_type))
        due_at = (
            last_uploaded + timedelta(days=schedule["days"])
            if last_uploaded
            else now
        )
        due_tests.append({
            "due_at": due_at,
            "upcoming_date": due_at.strftime("%d %b"),
            "upcoming_title": schedule["title"],
        })

    due_tests.sort(key=lambda item: item["due_at"])
    return [
        {
            "upcoming_date": test["upcoming_date"],
            "upcoming_title": test["upcoming_title"],
        }
        for test in due_tests[:2]
    ]


def build_dashboard(user_id, now=None):
    records = get_dashboard_records(user_id)
    user_row = records["user"]

    if user_row is None:
        return None

    reports = [report_to_dict(row) for row in records["reports"]]
    latest_report = records["reports"][-1] if records["reports"] else None
    previous_report = (
        records["reports"][-2]
        if len(records["reports"]) > 1
        else None
    )

    current_score = calculate_health_score(user_row, latest_report)
    previous_score = (
        calculate_health_score(user_row, previous_report)
        if previous_report
        else None
    )
    if previous_score is None:
        health_trend = None
    else:
        health_change = current_score - previous_score
        health_trend = "" if health_change == 0 else f"{health_change:+d} pts"

    latest_metrics = build_dashboard_metrics(reports)
    full_name = (user_row[0] or "").strip()

    return {
        "first_name": full_name.split()[0] if full_name else "",
        "health_score": {
            "score": current_score,
            "status": _health_status(current_score),
            "trend": health_trend,
        },
        "latest_metrics": latest_metrics,
        "ai_insights": _build_ai_insights(user_id, latest_metrics),
        "upcoming": _build_upcoming(
            records["uploads"],
            now or datetime.now(),
        ),
    }
