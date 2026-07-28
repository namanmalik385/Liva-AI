from collections import defaultdict
from datetime import date, datetime, timedelta

from db import get_timeline_records
from services.biomarker_service import METRIC_ORDER, metric_status
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


def _latest_metric(reports, metric):
    for report in reversed(reports):
        value = report.get(metric)
        if value is not None:
            return value
    return None


def _best_score(user_row, reports):
    if not reports:
        return None
    return max(
        calculate_health_score(user_row, _report_tuple(report))
        for report in reports
    )


def _period_snapshot(user_row, reports):
    return {
        "health_score": _best_score(user_row, reports),
        "metrics": {
            metric: _latest_metric(reports, metric)
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


def _trend_sub_summary(current_metrics, score_change):
    statuses = [
        metric_status(metric, value)
        for metric, value in current_metrics.items()
        if value is not None
    ]
    concerning = {
        "borderline",
        "elevated",
        "low",
        "positive",
        "abnormal",
    }
    has_concerning = any(status in concerning for status in statuses)

    if not statuses:
        return "No biomarker values are available for this period."
    if score_change is None:
        return (
            "Current biomarkers are available, but prior data is insufficient "
            "for comparison."
        )
    if score_change == 0 and not has_concerning:
        return "Biomarkers remain stable and within expected ranges."
    if score_change < 0 and has_concerning:
        return "Biomarkers have declined and some results need monitoring."
    if score_change < 0:
        return "Biomarkers have declined but remain within expected ranges."
    if has_concerning:
        return "Overall trend improved, though some biomarkers need monitoring."
    return "Biomarkers are improving and remain within expected ranges."


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
            "health_score": snapshot["health_score"],
            "biomarkers": {
                metric: {
                    "value": snapshot["metrics"][metric],
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
    score_change = (
        current["health_score"] - previous["health_score"]
        if (
            current["health_score"] is not None
            and previous["health_score"] is not None
        )
        else None
    )
    summary, default_sub_summary = _trend_text(
        current["health_score"],
        previous["health_score"],
        period,
    )

    return {
        "selected_period": period,
        "health_score": current["health_score"],
        "health_trend": _format_percent_change(
            current["health_score"],
            previous["health_score"],
        ),
        "trend_summary": summary,
        "trend_sub_summary": (
            default_sub_summary
            or _trend_sub_summary(current["metrics"], score_change)
        ),
        "biomarkers": {
            metric: {
                "value": current["metrics"][metric],
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
