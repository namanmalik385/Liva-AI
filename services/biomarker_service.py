REPORT_FIELDS = (
    "ast",
    "alt",
    "ggt",
    "bilirubin",
    "albumin",
    "platelets",
    "inr",
    "pt",
    "afp",
    "hbsag",
    "anti_hcv",
    "apri",
    "fib4",
    "ultrasound_prediction",
    "date_added",
)

METRIC_ORDER = (
    "fib4",
    "apri",
    "ast",
    "alt",
    "ggt",
    "bilirubin",
    "albumin",
    "platelets",
    "inr",
    "pt",
    "afp",
    "hbsag",
    "anti_hcv",
    "ultrasound_prediction",
)

METRIC_LABELS = {
    "fib4": "FIB-4",
    "apri": "APRI",
    "ast": "AST",
    "alt": "ALT",
    "ggt": "GGT",
    "bilirubin": "Bilirubin",
    "albumin": "Albumin",
    "platelets": "Platelets",
    "inr": "INR",
    "pt": "Prothrombin time",
    "afp": "AFP",
    "hbsag": "HBsAg",
    "anti_hcv": "Anti-HCV",
    "ultrasound_prediction": "Ultrasound",
}

METRIC_UNITS = {
    "fib4": None,
    "apri": None,
    "ast": "U/L",
    "alt": "U/L",
    "ggt": "U/L",
    "bilirubin": "mg/dL",
    "albumin": "g/dL",
    "platelets": "10^9/L",
    "inr": None,
    "pt": "seconds",
    "afp": "ng/mL",
    "hbsag": None,
    "anti_hcv": None,
    "ultrasound_prediction": None,
}


def report_to_dict(report_row):
    return dict(zip(REPORT_FIELDS, report_row))


def metric_status(metric, value):
    if value is None:
        return None

    if metric == "ultrasound_prediction":
        prediction = str(value).strip().lower()
        if not prediction:
            return None
        return "normal" if prediction == "normal" else "abnormal"

    if metric == "fib4":
        if value < 1.3:
            return "normal"
        if value < 2.67:
            return "borderline"
        return "elevated"

    if metric == "apri":
        if value < 0.5:
            return "normal"
        if value <= 1.5:
            return "borderline"
        return "elevated"

    if metric in ("ast", "alt", "ggt"):
        return "normal" if value <= 40 else "elevated"

    if metric == "bilirubin":
        if value < 0.2:
            return "low"
        if value <= 1.2:
            return "normal"
        return "elevated"

    if metric == "albumin":
        if value < 3.5:
            return "low"
        if value <= 5.0:
            return "normal"
        return "elevated"

    if metric == "platelets":
        if value < 150:
            return "low"
        if value <= 450:
            return "normal"
        return "elevated"

    if metric == "inr":
        if value < 0.8:
            return "low"
        if value <= 1.2:
            return "normal"
        return "elevated"

    if metric == "pt":
        if value < 11:
            return "low"
        if value <= 13.5:
            return "normal"
        return "elevated"

    if metric == "afp":
        return "normal" if value < 10 else "elevated"

    if metric in ("hbsag", "anti_hcv"):
        return "negative" if int(value) == 0 else "positive"

    return None


def _latest_values(reports, metric):
    values = [
        report.get(metric)
        for report in reversed(reports)
        if report.get(metric) is not None
    ]
    current = values[0] if values else None
    previous = values[1] if len(values) > 1 else None
    return current, previous


def _percent_change(current, previous):
    if current is None or previous is None:
        return None
    if previous == 0:
        return 0.0 if current == 0 else None
    return ((float(current) - float(previous)) / abs(float(previous))) * 100


def dashboard_metric_trend(current, previous, metric):
    if current is None or previous is None:
        return None

    if metric in ("hbsag", "anti_hcv", "ultrasound_prediction"):
        return "" if current == previous else "changed"

    change = _percent_change(current, previous)
    if change is None:
        return None
    if abs(change) < 0.05:
        return ""
    return f"{change:+.1f}%"


def report_metric_trend(current, previous, metric):
    if current is None:
        return None
    if previous is None:
        return None

    if metric in ("hbsag", "anti_hcv", "ultrasound_prediction"):
        return "stable" if current == previous else "changed"

    change = _percent_change(current, previous)
    if change is None:
        return None
    if abs(change) < 0.05:
        return "stable"

    direction = "increase" if change > 0 else "decrease"
    magnitude = f"{abs(change):.1f}".rstrip("0").rstrip(".")
    return f"{magnitude}% {direction}"


def build_dashboard_metrics(reports):
    latest_metrics = {}

    for metric in METRIC_ORDER:
        current, previous = _latest_values(reports, metric)
        latest_metrics[metric] = {
            "score": current,
            "status": metric_status(metric, current),
            "trend": dashboard_metric_trend(current, previous, metric),
        }

    return latest_metrics


def build_current_report_metrics(current_report, previous_report=None):
    biomarkers = {}
    previous_report = previous_report or {}

    for metric in METRIC_ORDER:
        current = current_report.get(metric)
        if current is None:
            biomarkers[metric] = {
                "value": None,
                "trend": None,
                "status": None,
                "insight": None,
            }
            continue

        biomarkers[metric] = {
            "value": current,
            "trend": report_metric_trend(
                current,
                previous_report.get(metric),
                metric,
            ),
            "status": metric_status(metric, current),
            "insight": None,
        }

    return biomarkers


def fallback_biomarker_insight(metric, metric_data):
    value = metric_data.get("value")
    status = metric_data.get("status")
    label = METRIC_LABELS[metric]

    if value is None:
        return None
    if status in ("normal", "negative"):
        return (
            f"Your {label} result is within the expected range in the "
            "current report."
        )
    if status == "borderline":
        return (
            f"Your {label} result is borderline and should be followed over "
            "time with your clinician."
        )
    if status == "low":
        return (
            f"Your {label} result is below the expected range and should be "
            "reviewed with your clinician."
        )
    if status in ("elevated", "positive", "abnormal"):
        return (
            f"Your {label} result needs monitoring and should be interpreted "
            "with the rest of your clinical information."
        )
    return f"Your current {label} result is available for clinical review."
