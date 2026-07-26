from db import (
    get_cached_report_analysis,
    get_report_analysis_records,
    save_report_analysis,
)
from llm import get_report_analysis
from services.biomarker_service import (
    METRIC_LABELS,
    build_current_report_metrics,
    fallback_biomarker_insight,
    report_to_dict,
)
from services.prompt_builder import calculate_health_score


ANALYSIS_VERSION = 2


class ReportNotFoundError(Exception):
    pass


def _health_status(score):
    if score >= 90:
        return "Healthy"
    if score >= 75:
        return "Good"
    if score >= 60:
        return "Needs Monitoring"
    if score >= 40:
        return "Concerning"
    return "Critical"


def _health_score_trend(current_score, previous_score):
    if previous_score is None:
        return None

    difference = current_score - previous_score
    if difference == 0:
        return "stable"

    direction = "higher" if difference > 0 else "lower"
    return f"{abs(difference)} pts {direction} than last report"


def _risk_level(health_score):
    risk_score = 100 - health_score

    if risk_score < 20:
        label = "Low"
        band = 1
    elif risk_score < 40:
        label = "Low Moderate"
        band = 2
    elif risk_score < 60:
        label = "Moderate"
        band = 3
    elif risk_score < 80:
        label = "High Moderate"
        band = 4
    else:
        label = "High"
        band = 5

    return {
        "value": risk_score,
        "label": label,
        "band": band,
        "scale_min": 0,
        "scale_max": 100,
    }


def _analysis_context(health_score, health_status, risk_level, biomarkers):
    current_biomarkers = {}

    for metric, data in biomarkers.items():
        if data["value"] is None:
            continue
        current_biomarkers[metric] = {
            "value": data["value"],
            "status": data["status"],
            "trend": data["trend"],
        }

    return {
        "health_score": health_score,
        "health_status": health_status,
        "risk_level": risk_level,
        "biomarkers": current_biomarkers,
    }


def _fallback_summary(health_status, biomarkers):
    available = [
        metric
        for metric, data in biomarkers.items()
        if data["value"] is not None
    ]
    needs_attention = [
        metric
        for metric in available
        if biomarkers[metric]["status"]
        not in ("normal", "negative")
    ]
    changed = [
        metric
        for metric in available
        if biomarkers[metric]["trend"]
        not in (None, "stable")
    ]

    if not available:
        return (
            "No biomarker values were available in the current report set. "
            "Upload and save a supported report before requesting analysis."
        )

    if needs_attention:
        labels = ", ".join(
            METRIC_LABELS[metric]
            for metric in needs_attention[:3]
        )
        summary = (
            f"Your current liver health status is {health_status}. "
            f"The current report contains results that need review: {labels}."
        )
    else:
        summary = (
            f"Your current liver health status is {health_status}. "
            "The available biomarkers are within their expected categories."
        )

    if changed:
        summary += (
            f" {len(changed)} recorded biomarker"
            f"{'s have' if len(changed) != 1 else ' has'} changed since the "
            "previous report."
        )

    summary += " Review these results with a qualified clinician."
    return summary


def _merge_narrative(biomarkers, narrative, health_status):
    insight_map = {}
    ai_summary = None

    if isinstance(narrative, dict) and not narrative.get("error"):
        candidate_insights = narrative.get("biomarker_insights")
        if isinstance(candidate_insights, dict):
            insight_map = candidate_insights

        candidate_summary = narrative.get("ai_summary")
        if isinstance(candidate_summary, str) and candidate_summary.strip():
            ai_summary = candidate_summary.strip()

    for metric, data in biomarkers.items():
        if data["value"] is None:
            continue

        candidate = insight_map.get(metric)
        data["insight"] = (
            candidate.strip()
            if isinstance(candidate, str) and candidate.strip()
            else fallback_biomarker_insight(metric, data)
        )

    return ai_summary or _fallback_summary(health_status, biomarkers)


def build_report_analysis(user_id, report_id=None):
    records = get_report_analysis_records(user_id, report_id)

    if records["user"] is None:
        return None
    if records["current"] is None:
        raise ReportNotFoundError

    current_record = records["current"]
    previous_record = records["previous"]
    current_report_id = current_record[0]

    current_row = current_record[1:]
    previous_row = previous_record[1:] if previous_record else None
    current_report = report_to_dict(current_row)
    previous_report = (
        report_to_dict(previous_row)
        if previous_row
        else None
    )

    health_score = calculate_health_score(records["user"], current_row)
    previous_score = (
        calculate_health_score(records["user"], previous_row)
        if previous_row
        else None
    )
    health_status = _health_status(health_score)
    risk_level = _risk_level(health_score)
    biomarkers = build_current_report_metrics(
        current_report,
        previous_report,
    )

    context = _analysis_context(
        health_score,
        health_status,
        risk_level,
        biomarkers,
    )
    narrative = get_cached_report_analysis(
        current_report_id,
        ANALYSIS_VERSION,
    )
    if narrative is None:
        narrative = get_report_analysis(context)
        if not (
            isinstance(narrative, dict)
            and narrative.get("error")
        ):
            save_report_analysis(
                current_report_id,
                ANALYSIS_VERSION,
                narrative,
            )

    ai_summary = _merge_narrative(
        biomarkers,
        narrative,
        health_status,
    )

    analysis = {
        "health_score": health_score,
        "health_status": health_status,
        "health_score_trend": _health_score_trend(
            health_score,
            previous_score,
        ),
        "risk_level": risk_level,
        "biomarkers": biomarkers,
        "ai_summary": ai_summary,
        "report_id": current_report_id,
    }

    return analysis
