from db import get_dashboard_records
from services.biomarker_service import METRIC_LABELS, METRIC_ORDER
from services.report_analysis_service import build_report_analysis


DECREASE_IS_POSITIVE = {
    "fib4",
    "apri",
    "ast",
    "alt",
    "bilirubin",
    "inr",
    "pt",
    "afp",
}

INCREASE_IS_POSITIVE = {
    "albumin",
    "platelets",
}


def _health_score_summary(analysis):
    trend = analysis["health_score_trend"]

    if trend is None:
        return (
            "Your first liver health score is ready. Continue healthy "
            "lifestyle habits and routine monitoring."
        )
    if trend == "stable":
        return (
            "Your liver health remains stable. Continue healthy lifestyle "
            "habits and routine monitoring."
        )
    if "higher" in trend:
        return (
            "Your liver health score has improved since the last report. "
            "Continue your current healthy habits."
        )
    return (
        "Your liver health score is lower than the last report. Review the "
        "changes and continue close monitoring."
    )


def _current_health_status(analysis):
    biomarkers = analysis["biomarkers"]
    risk_label = analysis["risk_level"]["label"]

    needs_attention = [
        metric
        for metric, data in biomarkers.items()
        if data["value"] is not None
        and data["status"] not in ("normal", "non-reactive")
    ]

    if needs_attention:
        biomarker_status = (
            f"{len(needs_attention)} biomarker"
            f"{'s' if len(needs_attention) != 1 else ''} need monitoring"
        )
    else:
        biomarker_status = "Stable biomarkers"

    albumin = biomarkers["albumin"]
    if albumin["value"] is None:
        albumin_status = "Albumin not recorded"
    elif albumin["status"] == "normal":
        albumin_status = "Normal albumin"
    else:
        albumin_status = f"{albumin['status'].title()} albumin"

    ultrasound = biomarkers["ultrasound_prediction"]
    critical = (
        analysis["health_status"] == "Critical"
        or (
            isinstance(ultrasound["value"], str)
            and "hcc" in ultrasound["value"].lower()
        )
    )

    return [
        f"{risk_label} liver risk",
        biomarker_status,
        albumin_status,
        (
            "Critical findings need review"
            if critical
            else "No critical findings"
        ),
    ]


def _biomarker_clinical_insights(analysis):
    return {
        metric: {
            "score": data["value"],
            "status": data["status"],
            "summary": data["insight"],
        }
        for metric, data in analysis["biomarkers"].items()
    }


def _trend_parts(trend):
    if not isinstance(trend, str) or "%" not in trend:
        return None, None

    magnitude, direction = trend.split("%", 1)
    try:
        percent = float(magnitude)
    except ValueError:
        return None, None

    return percent, direction.strip()


def _positive_metric_changes(biomarkers):
    changes = []

    for metric in METRIC_ORDER:
        data = biomarkers[metric]
        trend = data["trend"]
        percent, direction = _trend_parts(trend)

        is_positive = (
            direction == "decrease"
            and metric in DECREASE_IS_POSITIVE
        ) or (
            direction == "increase"
            and metric in INCREASE_IS_POSITIVE
        )

        if is_positive:
            percentage = f"{percent:g}%"
            changes.append({
                "title": f"{METRIC_LABELS[metric]} improved {percentage}",
                "subtitle": "vs last report",
            })

        if (
            metric in ("hbsag", "anti_hcv")
            and trend == "changed"
            and data["status"] == "non-reactive"
        ):
            changes.append({
                "title": f"{METRIC_LABELS[metric]} now non-reactive",
                "subtitle": "vs last report",
            })

        if (
            metric == "ultrasound_prediction"
            and trend == "changed"
            and data["status"] == "normal"
        ):
            changes.append({
                "title": "Ultrasound now normal",
                "subtitle": "vs last report",
            })

    return changes


def _monitoring_history(report_rows):
    report_count = len(report_rows)

    if report_count >= 2:
        return {
            "title": "Consistent monitoring",
            "subtitle": f"{report_count} reports tracked",
        }
    return {
        "title": "Baseline recorded",
        "subtitle": "Ready for future comparison",
    }


def _positive_changes(analysis, report_rows):
    biomarkers = analysis["biomarkers"]
    changes = _positive_metric_changes(biomarkers)
    score_trend = analysis["health_score_trend"]

    if score_trend and "higher" in score_trend:
        points = score_trend.split(" ", 1)[0]
        changes.append({
            "title": "Health score increased",
            "subtitle": f"+{points} points",
        })
    elif score_trend == "stable":
        changes.append({
            "title": "Health score maintained",
            "subtitle": "Stable since last report",
        })

    changes.append(_monitoring_history(report_rows))

    normal_metrics = [
        metric
        for metric in METRIC_ORDER
        if biomarkers[metric]["value"] is not None
        and biomarkers[metric]["status"] in ("normal", "non-reactive")
    ]
    for metric in normal_metrics:
        if len(changes) >= 4:
            break
        changes.append({
            "title": f"{METRIC_LABELS[metric]} within range",
            "subtitle": "Current report",
        })

    fallbacks = (
        {
            "title": "Current report reviewed",
            "subtitle": "Latest values analyzed",
        },
        {
            "title": "Trend tracking active",
            "subtitle": "Future changes will be compared",
        },
        {
            "title": "Health baseline available",
            "subtitle": "Supports routine monitoring",
        },
    )
    for fallback in fallbacks:
        if len(changes) >= 4:
            break
        changes.append(fallback)

    return changes[:4]


def _risk_factors(analysis, user_row):
    biomarkers = analysis["biomarkers"]
    factors = []

    subtitles = {
        "borderline": "Monitor trend closely",
        "elevated": "Review with your clinician",
        "low": "Review with your clinician",
        "reactive": "Clinical follow-up advised",
        "abnormal": "Imaging review advised",
    }

    for metric in METRIC_ORDER:
        data = biomarkers[metric]
        status = data["status"]
        if data["value"] is None or status not in subtitles:
            continue
        factors.append({
            "title": f"{METRIC_LABELS[metric]} {status}",
            "subtitle": subtitles[status],
        })
        if len(factors) == 4:
            return factors

    (
        _name,
        _age,
        _gender,
        _weight,
        _height,
        bmi,
        diabetes,
        hypertension,
        previous_liver_disease,
        family_history,
        _activity,
        _exercise,
        alcohol,
        smoking,
    ) = user_row

    profile_factors = []
    if previous_liver_disease:
        profile_factors.append(("Previous liver disease", "Continue clinical follow-up"))
    if diabetes:
        profile_factors.append(("Diabetes", "Maintain metabolic control"))
    if hypertension:
        profile_factors.append(("Hypertension", "Maintain blood pressure control"))
    if family_history:
        profile_factors.append(("Family history", "Continue routine screening"))
    if bmi is not None and bmi >= 25:
        profile_factors.append(("Elevated BMI", "Support healthy weight management"))
    if alcohol in ("moderate", "heavy"):
        profile_factors.append(("Alcohol intake", "Consider reducing consumption"))
    if smoking == "current":
        profile_factors.append(("Current smoking", "Smoking cessation is recommended"))

    for title, subtitle in profile_factors:
        if len(factors) == 4:
            break
        factors.append({
            "title": title,
            "subtitle": subtitle,
        })

    if not factors:
        factors.append({
            "title": "No major recorded risks",
            "subtitle": "Maintain routine monitoring",
        })

    return factors


def _areas_to_monitor(analysis, user_row):
    biomarkers = analysis["biomarkers"]
    areas = []

    if any(
        biomarkers[metric]["status"] in ("borderline", "elevated")
        for metric in ("fib4", "apri")
    ):
        areas.append("Fibrosis Risk")

    if any(
        biomarkers[metric]["status"] == "elevated"
        for metric in ("ast", "alt")
    ):
        areas.append("Liver Enzymes")

    bmi = user_row[5]
    if bmi is not None and bmi >= 25:
        areas.append("Weight Management")

    if any(
        data["trend"] not in (None, "stable")
        for data in biomarkers.values()
    ):
        areas.append("Biomarker Trends")

    areas.append("Follow-up Testing")

    defaults = (
        "Healthy Lifestyle",
        "Routine Monitoring",
        "Preventive Care",
        "Biomarker Trends",
    )
    for area in defaults:
        if len(areas) >= 4:
            break
        if area not in areas:
            areas.append(area)

    return areas[:4]


def _recommendation(analysis, areas):
    biomarkers = analysis["biomarkers"]
    monitor_labels = [
        METRIC_LABELS[metric]
        for metric in METRIC_ORDER
        if biomarkers[metric]["value"] is not None
        and biomarkers[metric]["status"]
        not in ("normal", "non-reactive")
    ]

    recommendation = (
        f"Your overall liver health status is "
        f"{analysis['health_status'].lower()}."
    )

    if monitor_labels:
        recommendation += (
            f" Continue monitoring {', '.join(monitor_labels[:3])}."
        )
    else:
        recommendation += (
            " Continue routine biomarker monitoring."
        )

    if "Weight Management" in areas:
        recommendation += (
            " Maintain physical activity and healthy nutrition to support "
            "weight management."
        )
    else:
        recommendation += (
            " Maintain physical activity and healthy nutrition."
        )

    recommendation += (
        " Schedule follow-up testing according to your clinician's advice."
    )
    return recommendation


def build_health_insights(user_id, report_id=None):
    analysis = build_report_analysis(user_id, report_id)
    if analysis is None:
        return None

    records = get_dashboard_records(user_id)
    user_row = records["user"]
    areas = _areas_to_monitor(analysis, user_row)

    return {
        "health_score": analysis["health_score"],
        "health_score_status": analysis["health_status"],
        "health_score_summary": _health_score_summary(analysis),
        "current_health_status": _current_health_status(analysis),
        "biomarker_clinical_insights": _biomarker_clinical_insights(
            analysis
        ),
        "positive_changes": _positive_changes(
            analysis,
            records["reports"],
        ),
        "risk_factors": _risk_factors(analysis, user_row),
        "areas_to_monitor": areas,
        "recommendation": _recommendation(analysis, areas),
    }
