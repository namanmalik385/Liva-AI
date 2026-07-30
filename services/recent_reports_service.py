from datetime import date, datetime


REPORT_TITLES = {
    "lft": "Liver Function Test",
    "cbc": "Complete Blood Count",
    "coagulation": "Coagulation Report",
    "afp": "AFP Test",
    "hepatitis": "Hepatitis Test",
    "ultrasound": "Ultrasound Report",
}

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

DATE_FORMATS = (
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def format_date_uploaded(value):
    parsed = None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif value is not None:
        text = str(value).strip()
        if text:
            try:
                parsed = datetime.fromisoformat(
                    text.replace("Z", "+00:00")
                ).date()
            except ValueError:
                for input_format in DATE_FORMATS:
                    try:
                        parsed = datetime.strptime(
                            text,
                            input_format,
                        ).date()
                        break
                    except ValueError:
                        continue

    if parsed is None:
        return value
    return (
        f"{MONTH_NAMES[parsed.month - 1]} "
        f"{parsed.day}, {parsed.year}"
    )


def format_recent_reports(reports):
    output = []
    for report in reports:
        formatted = dict(report)
        mime_type = formatted.get("mime_type")
        formatted["title"] = REPORT_TITLES.get(
            formatted.get("report_type"),
            "Health Report",
        )
        formatted["date_uploaded"] = format_date_uploaded(
            formatted.get("date_uploaded")
        )
        if mime_type == "application/pdf":
            formatted["viewer_type"] = "pdf"
        elif isinstance(mime_type, str) and mime_type.startswith("image/"):
            formatted["viewer_type"] = "image"
        else:
            formatted["viewer_type"] = None
        output.append(formatted)
    return output
