from db import create_support_ticket


MAX_DESCRIPTION_LENGTH = 4000

SUBJECT_ALIASES = {
    "application issue": "Application Issue",
    "report upload query": "Report Upload Query",
    "ai health assessment explanation": (
        "AI Health Assessment Explanation"
    ),
    "other support query": "Other Support Query",
    "other support queries": "Other Support Query",
}


class SupportValidationError(ValueError):
    pass


def _normalize_subject(value):
    if not isinstance(value, str):
        raise SupportValidationError("subject must be a string")

    normalized = " ".join(value.strip().casefold().split())
    subject = SUBJECT_ALIASES.get(normalized)
    if subject is None:
        allowed = ", ".join(dict.fromkeys(SUBJECT_ALIASES.values()))
        raise SupportValidationError(
            f"subject must be one of: {allowed}"
        )
    return subject


def _normalize_description(data):
    has_description = "description" in data
    has_message = "message" in data

    if has_description and has_message:
        raise SupportValidationError(
            "Provide description or message, not both"
        )
    if not has_description and not has_message:
        raise SupportValidationError("description is required")

    value = data.get("description") if has_description else data.get("message")
    if not isinstance(value, str):
        raise SupportValidationError("description must be a string")

    description = value.strip()
    if not description:
        raise SupportValidationError("description is required")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise SupportValidationError(
            "description must be 4000 characters or fewer"
        )
    return description


def validate_support_request(data):
    if not isinstance(data, dict):
        raise SupportValidationError("A JSON request body is required")

    unsupported = sorted(
        set(data) - {"subject", "description", "message"}
    )
    if unsupported:
        raise SupportValidationError(
            f"Unsupported fields: {', '.join(unsupported)}"
        )
    if "subject" not in data:
        raise SupportValidationError("subject is required")

    return {
        "subject": _normalize_subject(data["subject"]),
        "description": _normalize_description(data),
    }


def submit_support_request(user_id, data):
    request_data = validate_support_request(data)
    ticket = create_support_ticket(
        user_id,
        request_data["subject"],
        request_data["description"],
    )
    ticket["created_at"] = ticket["created_at"].isoformat()
    return ticket
