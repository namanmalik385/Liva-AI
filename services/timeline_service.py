from collections import defaultdict
from datetime import date, datetime, timedelta

from db import get_timeline_records
from services.biomarker_service import (
    METRIC_ORDER,
    metric_response_value,
    metric_status,
)
from services.prompt_builder import calculate_health_score


TIMELINE_PERIODS = ("weekly", "monthly", "yearly")
HISTORY_METRICS = ("ast", "alt", "bilirubin", "albumin", "ggt")
ALL_TIMELINE_METRICS = tuple(METRIC_ORDER)
CATEGORICAL_METRICS = (
    "hbsag",
    "anti_hcv",
    "ultrasound_prediction",
)


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _report_tuple(report):
    """Adapt a timeline report to the existing health-score calculator."""
    return (
        report.get("ast"),
        report.get("alt"),
        report.get("ggt"),
        report.get("bilirubin"),
        report.get("albumin"),
        report.get("platelets"),
        report.get("inr"),
        report.get("pt"),
        report.get("afp"),
        report.get("hbsag"),
        report.get("anti_hcv"),
        report.get("apri"),
        report.get("fib4"),
        report.get("ultrasound_prediction"),
        report.get("date_added"),
    )


def _format_percent_change(current, previous):
    if current is None or previous is None:
        return None
    if previous == 0:
        return "stable" if current == 0 else None

    change = ((float(current) - float(previous)) / abs(float(previous))) * 100
    if abs(change) < 0.05:
        return "stable"
    magnitude = f"{change:+.1f}".rstrip("0").rstrip(".")
    return f"{magnitude}%"


def _metric_trend(metric, current, previous):
    if current is None or previous is None:
        return None
    if metric in CATEGORICAL_METRICS:
        return "stable" if current == previous else "changed"
    return _format_percent_change(current, previous)


def _previous_key(period, key):
    if period == "weekly":
        return key - timedelta(days=7)
    if period == "monthly":
        year, month = key
        return (year - 1, 12) if month == 1 else (year, month - 1)
    return key - 1


def _key_for(period, report_date):
    if period == "weekly":
        return report_date - timedelta(days=report_date.weekday())
    if period == "monthly":
        return report_date.year, report_date.month
    return report_date.year


def _display_periods(period, today, report_dates):
    if period == "weekly":
        current_week = today - timedelta(days=today.weekday())
        return [
            {
                "key": current_week - timedelta(weeks=offset),
                "period": f"Week {4 - offset}",
                "label": (
                    current_week - timedelta(weeks=offset)
                ).strftime("%d %b"),
                "start_date": (
                    current_week - timedelta(weeks=offset)
                ).isoformat(),
                "end_date": (
                    current_week
                    - timedelta(weeks=offset)
                    + timedelta(days=6)
                ).isoformat(),
            }
            for offset in range(3, -1, -1)
        ]

    if period == "monthly":
        return [
            {
                "key": (today.year, month),
                "period": datetime(today.year, month, 1).strftime("%B"),
                "label": datetime(today.year, month, 1).strftime("%B"),
            }
            for month in range(1, 13)
        ]

    years = sorted({report_date.year for report_date in report_dates})
    return [
        {
            "key": year,
            "period": str(year),
            "label": str(year),
        }
        for year in years
    ]


def _best_score(user_row, reports):
    if not reports:
        return None
    return max(
        calculate_health_score(user_row, _report_tuple(report))
        for report in reports
    )


def _latest_score(user_row, reports):
    if not reports:
        return None
    return calculate_health_score(user_row, _report_tuple(reports[-1]))


def _period_snapshot(user_row, reports):
    latest_report = reports[-1] if reports else {}
    return {
        "best_health_score": _best_score(user_row, reports),
        "latest_health_score": _latest_score(user_row, reports),
        "metrics": {
            metric: latest_report.get(metric)
            for metric in ALL_TIMELINE_METRICS
        },
    }


def _trend_text(current_score, previous_score, period):
    comparison = {
        "weekly": "last week",
        "monthly": "last month",
        "yearly": "last year",
    }[period]

    if current_score is None:
        return (
            "No health score is available for this period.",
            "Upload a report to begin tracking your liver health.",
        )
    if previous_score is None:
        return (
            "Not enough data is available to calculate a health trend.",
            "Another report is needed for a period-to-period comparison.",
        )

    difference = current_score - previous_score
    if difference > 0:
        summary = (
            f"Liver health score improved by {difference} points since "
            f"{comparison}."
        )
    elif difference < 0:
        summary = (
            f"Liver health score worsened by {abs(difference)} points since "
            f"{comparison}."
        )
    else:
        summary = f"Liver health score remained stable since {comparison}."

    return summary, None


STATUS_SEVERITY = {
    "normal": 0,
    "non-reactive": 0,
    "borderline": 1,
    "low": 2,
    "elevated": 2,
    "reactive": 2,
    "abnormal": 2,
}


def _metric_movement(metric, current, previous):
    if current is None or previous is None:
        return None
    if current == previous:
        return "stable"

    current_status = metric_status(metric, current)
    previous_status = metric_status(metric, previous)
    current_severity = STATUS_SEVERITY.get(current_status)
    previous_severity = STATUS_SEVERITY.get(previous_status)

    if (
        current_severity is not None
        and previous_severity is not None
        and current_severity != previous_severity
    ):
        return (
            "improved"
            if current_severity < previous_severity
            else "worsened"
        )

    if current_status in ("normal", "non-reactive"):
        return "stable"
    if metric in CATEGORICAL_METRICS:
        return "stable"

    if current_status == "low":
        return "improved" if current > previous else "worsened"

    return "improved" if current < previous else "worsened"


def _trend_sub_summary(current_metrics, previous_metrics):
    available = [
        metric
        for metric, value in current_metrics.items()
        if value is not None
    ]
    if not available:
        return "No biomarker values are available for this period."

    movements = [
        _metric_movement(
            metric,
            current_metrics[metric],
            previous_metrics.get(metric),
        )
        for metric in available
    ]
    comparable = [movement for movement in movements if movement is not None]
    if not comparable:
        return (
            "Current biomarkers are available, but prior data is insufficient "
            "for comparison."
        )

    improved = comparable.count("improved")
    worsened = comparable.count("worsened")
    concerning = sum(
        metric_status(metric, current_metrics[metric])
        in {"borderline", "elevated", "low", "reactive", "abnormal"}
        for metric in available
    )

    if worsened == 0 and improved == 0 and concerning == 0:
        return "Biomarkers remain stable and within expected ranges."
    if worsened >= 2 and worsened > improved and concerning >= 2:
        return "Biomarkers have significantly declined and need monitoring."
    if worsened > improved and concerning:
        return "Biomarkers have declined and some results need monitoring."
    if worsened > improved:
        return "Biomarkers have declined but remain within expected ranges."
    if improved > worsened and concerning:
        return "Overall trend improved, though some biomarkers need monitoring."
    if improved > worsened:
        return "Biomarkers are improving and remain within expected ranges."
    if concerning:
        return "Biomarkers are mixed and some results need monitoring."
    return "Biomarker changes are mixed but remain within expected ranges."


def build_timeline(user_id, period, now=None):
    records = get_timeline_records(user_id)
    user_row = records["user"]
    if user_row is None:
        return None

    today = (now or datetime.now()).date()
    reports = []
    for report in records["reports"]:
        parsed_date = _parse_datetime(report.get("date_added"))
        if parsed_date is None:
            continue
        normalized = dict(report)
        normalized["_date"] = parsed_date.date()
        reports.append(normalized)
    reports.sort(key=lambda item: (item["_date"], item.get("id", 0)))

    grouped = defaultdict(list)
    for report in reports:
        grouped[_key_for(period, report["_date"])].append(report)

    periods = _display_periods(
        period,
        today,
        [report["_date"] for report in reports],
    )
    snapshots = {
        key: _period_snapshot(user_row, period_reports)
        for key, period_reports in grouped.items()
    }

    history = []
    for period_data in periods:
        key = period_data["key"]
        snapshot = snapshots.get(key, _period_snapshot(user_row, []))
        previous = snapshots.get(
            _previous_key(period, key),
            _period_snapshot(user_row, []),
        )
        history.append({
            **{
                name: value
                for name, value in period_data.items()
                if name != "key"
            },
            "health_score": snapshot["latest_health_score"],
            "biomarkers": {
                metric: {
                    "value": metric_response_value(
                        metric,
                        snapshot["metrics"][metric],
                    ),
                    "trend": _metric_trend(
                        metric,
                        snapshot["metrics"][metric],
                        previous["metrics"][metric],
                    ),
                }
                for metric in HISTORY_METRICS
            },
        })

    current_key = _key_for(period, today)
    current = snapshots.get(
        current_key,
        _period_snapshot(user_row, []),
    )
    previous = snapshots.get(
        _previous_key(period, current_key),
        _period_snapshot(user_row, []),
    )
    summary, default_sub_summary = _trend_text(
        current["latest_health_score"],
        previous["latest_health_score"],
        period,
    )

    return {
        "selected_period": period,
        "health_score": current["best_health_score"],
        "health_trend": _format_percent_change(
            current["latest_health_score"],
            previous["latest_health_score"],
        ),
        "trend_summary": summary,
        "trend_sub_summary": (
            default_sub_summary
            or _trend_sub_summary(
                current["metrics"],
                previous["metrics"],
            )
        ),
        "biomarkers": {
            metric: {
                "value": metric_response_value(
                    metric,
                    current["metrics"][metric],
                ),
                "trend": _metric_trend(
                    metric,
                    current["metrics"][metric],
                    previous["metrics"][metric],
                ),
            }
            for metric in ALL_TIMELINE_METRICS
        },
        "health_history": history,
    }
