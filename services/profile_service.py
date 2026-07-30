from datetime import date, datetime

from db import get_profile_summary_records, update_user_personal_info
from services.biomarker_service import (
    METRIC_ORDER,
    metric_status,
    report_to_dict,
)
from services.prompt_builder import calculate_health_score


CORE_PROFILE_METRICS = (
    "ast",
    "alt",
    "bilirubin",
    "albumin",
    "platelets",
)
EDITABLE_PERSONAL_FIELDS = {"full_name", "age", "gender"}
ALLOWED_GENDERS = {"male", "female", "other"}


class ProfileValidationError(ValueError):
    pass


def validate_personal_info_update(data):
    if not isinstance(data, dict):
        raise ProfileValidationError("A JSON request body is required")
    if not data:
        raise ProfileValidationError(
            "At least one profile field is required"
        )

    unsupported = sorted(set(data) - EDITABLE_PERSONAL_FIELDS)
    if unsupported:
        raise ProfileValidationError(
            f"Unsupported profile fields: {', '.join(unsupported)}"
        )

    updates = {}
    if "full_name" in data:
        value = data["full_name"]
        if not isinstance(value, str):
            raise ProfileValidationError("full_name must be a string")
        full_name = " ".join(value.strip().split())
        if len(full_name) < 2 or len(full_name) > 100:
            raise ProfileValidationError(
                "full_name must be between 2 and 100 characters"
            )
        updates["full_name"] = full_name

    if "age" in data:
        value = data["age"]
        if isinstance(value, bool):
            raise ProfileValidationError("age must be a whole number")
        try:
            age = float(value)
        except (TypeError, ValueError) as error:
            raise ProfileValidationError(
                "age must be a whole number"
            ) from error
        if not age.is_integer():
            raise ProfileValidationError("age must be a whole number")
        if age < 13 or age > 120:
            raise ProfileValidationError(
                "age must be between 13 and 120"
            )
        updates["age"] = int(age)

    if "gender" in data:
        value = data["gender"]
        if not isinstance(value, str):
            raise ProfileValidationError("gender must be a string")
        gender = " ".join(value.strip().casefold().split())
        if gender not in ALLOWED_GENDERS:
            raise ProfileValidationError(
                "gender must be one of: female, male, other"
            )
        updates["gender"] = gender

    return updates


def _liver_health_status(score):
    if score >= 80:
        return "Healthy"
    if score >= 60:
        return "Needs Improvement"
    if score >= 40:
        return "At Risk"
    return "Critical"


def _is_critical_biomarker(metric, value):
    if value is None:
        return False

    if metric in ("ast", "alt", "ggt"):
        return value > 120
    if metric == "bilirubin":
        return value > 3
    if metric == "albumin":
        return value < 3
    if metric == "platelets":
        return value < 100
    if metric == "inr":
        return value > 1.5
    if metric == "pt":
        return value > 15
    if metric == "afp":
        return value >= 400
    if metric == "apri":
        return value > 1.5
    if metric == "fib4":
        return value >= 2.67
    if metric == "ultrasound_prediction":
        return "hcc" in str(value).strip().lower()
    return False


def _biomarkers_status(report):
    if not report:
        return "Monitor"

    available = {
        metric: report.get(metric)
        for metric in METRIC_ORDER
        if report.get(metric) is not None
    }
    if not available:
        return "Monitor"

    if any(
        _is_critical_biomarker(metric, value)
        for metric, value in available.items()
    ):
        return "Critical"

    if any(report.get(metric) is None for metric in CORE_PROFILE_METRICS):
        return "Monitor"

    concerning = {
        "borderline",
        "elevated",
        "low",
        "reactive",
        "abnormal",
    }
    if any(
        metric_status(metric, value) in concerning
        for metric, value in available.items()
    ):
        return "Monitor"

    return "Stable"


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


def build_profile(user_id, now=None):
    records = get_profile_summary_records(user_id)
    user_row = records["user"]
    if user_row is None:
        return None

    latest_row = records["latest_report"]
    latest_report = report_to_dict(latest_row) if latest_row else None
    health_score = calculate_health_score(user_row, latest_row)

    display_date = (
        _parse_datetime(latest_report.get("date_added"))
        if latest_report
        else None
    )
    if display_date is None:
        display_date = _parse_datetime(records.get("latest_upload_date"))
    if display_date is None:
        display_date = now or datetime.now()

    return {
        "full_name": (user_row[0] or "").strip(),
        "age": user_row[1],
        "gender": user_row[2],
        "health_score": health_score,
        "total_uploaded_reports": records["total_uploaded_reports"],
        "liver_health_status": _liver_health_status(health_score),
        "biomarkers_status": _biomarkers_status(latest_report),
        "month_year": display_date.strftime("%B %Y"),
    }


def update_personal_info(user_id, data):
    updates = validate_personal_info_update(data)
    updated = update_user_personal_info(user_id, updates)
    if updated is None:
        return None
    return build_profile(user_id)
