import os
import uuid

from calculators.apri import calculate_apri
from calculators.fib4 import calculate_fib4
from db import (
    complete_report_batch,
    create_or_get_report_batch,
    get_user_profile_record,
    mark_report_batch_failed,
)
from services.biomarker_service import metric_status


LAB_REPORT_TYPES = {
    "lft",
    "cbc",
    "coagulation",
    "afp",
    "hepatitis",
}
SUPPORTED_REPORT_TYPES = LAB_REPORT_TYPES | {"ultrasound"}
LAB_EXTENSIONS = {".pdf"}
ULTRASOUND_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_BATCH_FILES = int(os.getenv("MAX_BATCH_FILES", "6"))
UPLOAD_FOLDER = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "uploads")
)

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
    "ast_uln",
    "ultrasound_prediction",
)

TYPE_FIELDS = {
    "lft": {
        "ast",
        "alt",
        "ggt",
        "total_bilirubin",
        "albumin",
        "ast_uln",
    },
    "cbc": {"platelets"},
    "coagulation": {"inr", "pt"},
    "afp": {"afp"},
    "hepatitis": {"hbsag", "anti_hcv"},
    "ultrasound": {"ultrasound_prediction"},
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


class ReportBatchError(Exception):
    def __init__(self, message, status_code=400, batch_id=None):
        super().__init__(message)
        self.status_code = status_code
        self.batch_id = batch_id


def validate_idempotency_key(value):
    if not isinstance(value, str) or not value.strip():
        raise ReportBatchError("Idempotency-Key header is required")
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError) as error:
        raise ReportBatchError(
            "Idempotency-Key must be a valid UUID"
        ) from error


def validate_batch_manifest(files, report_types):
    if not files:
        raise ReportBatchError("At least one file is required")
    if len(files) > MAX_BATCH_FILES:
        raise ReportBatchError(
            f"A maximum of {MAX_BATCH_FILES} files is allowed"
        )
    if len(files) != len(report_types):
        raise ReportBatchError(
            "files and report_types must contain the same number of items"
        )

    normalized_types = []
    for index, report_type in enumerate(report_types):
        if not isinstance(report_type, str) or not report_type.strip():
            raise ReportBatchError(
                f"report_types item {index + 1} is required"
            )
        normalized = report_type.strip().lower()
        if normalized not in SUPPORTED_REPORT_TYPES:
            raise ReportBatchError(
                f"Unsupported report type: {normalized}"
            )
        normalized_types.append(normalized)

    if len(set(normalized_types)) != len(normalized_types):
        raise ReportBatchError(
            "Only one file per report type is allowed in a batch"
        )

    for index, file in enumerate(files):
        if file is None or not getattr(file, "filename", ""):
            raise ReportBatchError(
                f"files item {index + 1} has no filename"
            )

    return normalized_types


def _validated_extension(file, report_type):
    extension = os.path.splitext(file.filename or "")[1].lower()
    allowed_extensions = (
        ULTRASOUND_EXTENSIONS
        if report_type == "ultrasound"
        else LAB_EXTENSIONS
    )
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ReportBatchError(
            f"{report_type} must use one of these file types: {allowed}"
        )

    header = file.stream.read(8)
    file.stream.seek(0)
    is_pdf = header.startswith(b"%PDF-")
    is_image = (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
    )
    if report_type == "ultrasound" and not is_image:
        raise ReportBatchError(
            "The ultrasound must be a valid JPEG or PNG image"
        )
    if report_type != "ultrasound" and not is_pdf:
        raise ReportBatchError(
            f"The {report_type} report must be a valid PDF"
        )
    return extension


def _extract_file(filepath, report_type):
    if report_type == "ultrasound":
        from services.ultrasound_model import predict_liver_condition

        return {
            "ultrasound_prediction": predict_liver_condition(filepath)
        }

    from services.text_extractor import extract_text

    text = extract_text(filepath)
    if report_type == "lft":
        from parsers.lft_parser import parse_lft

        return parse_lft(text)
    if report_type == "cbc":
        from parsers.cbc_parser import parse_cbc

        return parse_cbc(text)
    if report_type == "coagulation":
        from parsers.coagulation_parser import parse_coagulation

        return parse_coagulation(text)
    if report_type == "afp":
        from parsers.afp_parser import parse_afp

        return parse_afp(text)

    from parsers.hepatitis_parser import parse_hepatitis

    return parse_hepatitis(text)


def _normalize_extracted_data(report_type, extracted):
    normalized = {}
    for key in TYPE_FIELDS[report_type]:
        value = extracted.get(key)
        output_key = "bilirubin" if key == "total_bilirubin" else key
        normalized[output_key] = value
    return normalized


def _has_extracted_value(extracted):
    return any(value is not None for value in extracted.values())


def calculate_batch_metrics(age, report_data):
    fib4_missing = [
        field
        for field in ("age", "ast", "alt", "platelets")
        if (
            age if field == "age" else report_data.get(field)
        ) is None
    ]
    if report_data.get("alt") is not None and report_data["alt"] <= 0:
        fib4_missing.append("alt")
    if report_data.get("ast") is not None and report_data["ast"] < 0:
        fib4_missing.append("ast")
    if (
        report_data.get("platelets") is not None
        and report_data["platelets"] <= 0
    ):
        fib4_missing.append("platelets")
    fib4_missing = list(dict.fromkeys(fib4_missing))

    fib4 = None
    if not fib4_missing:
        fib4 = round(calculate_fib4(
            age=age,
            ast=report_data["ast"],
            alt=report_data["alt"],
            platelets=report_data["platelets"],
        ), 2)

    apri_missing = [
        field
        for field in ("ast", "ast_uln", "platelets")
        if report_data.get(field) is None
    ]
    if (
        report_data.get("ast_uln") is not None
        and report_data["ast_uln"] <= 0
    ):
        apri_missing.append("ast_uln")
    if report_data.get("ast") is not None and report_data["ast"] < 0:
        apri_missing.append("ast")
    if (
        report_data.get("platelets") is not None
        and report_data["platelets"] <= 0
    ):
        apri_missing.append("platelets")
    apri_missing = list(dict.fromkeys(apri_missing))

    apri = None
    if not apri_missing:
        apri = round(calculate_apri(
            ast=report_data["ast"],
            ast_uln=report_data["ast_uln"],
            platelets=report_data["platelets"],
        ), 2)

    return {
        "fib4": {
            "value": fib4,
            "status": metric_status("fib4", fib4),
            "missing_inputs": fib4_missing,
        },
        "apri": {
            "value": apri,
            "status": metric_status("apri", apri),
            "missing_inputs": apri_missing,
        },
    }


def _public_file_results(file_results):
    return [
        {
            "file_index": item["file_index"],
            "report_type": item["report_type"],
            "status": item["status"],
            "extracted_fields": sorted(
                key
                for key, value in item["extracted_data"].items()
                if value is not None
            ),
        }
        for item in file_results
    ]


def _build_response(batch_id, file_results, report_data, calculations):
    biomarkers = {
        field: report_data.get(field)
        for field in REPORT_FIELDS
        if field != "ast_uln"
    }
    return {
        "success": True,
        "batch": {
            "batch_id": batch_id,
            "status": "completed",
            "file_count": len(file_results),
            "files": _public_file_results(file_results),
        },
        "report": {
            "report_id": None,
            "calculated_metrics": calculations,
            "biomarkers": biomarkers,
        },
    }


def process_report_batch(user_id, files, report_types, idempotency_key):
    normalized_key = validate_idempotency_key(idempotency_key)
    normalized_types = validate_batch_manifest(files, report_types)
    batch_id = str(uuid.uuid4())
    batch_record = create_or_get_report_batch(
        batch_id,
        user_id,
        normalized_key,
        len(files),
    )

    if not batch_record["created"]:
        if (
            batch_record["status"] == "completed"
            and isinstance(batch_record["response"], dict)
        ):
            replay = dict(batch_record["response"])
            replay["idempotent_replay"] = True
            return replay, 200
        if batch_record["status"] == "processing":
            raise ReportBatchError(
                "This report batch is already processing",
                409,
                batch_record["batch_id"],
            )
        raise ReportBatchError(
            batch_record["error_message"]
            or "This report batch previously failed; use a new key",
            409,
            batch_record["batch_id"],
        )

    batch_id = batch_record["batch_id"]
    temporary_paths = []
    file_results = []

    try:
        profile = get_user_profile_record(user_id)
        age = profile[1] if profile else None
        if age is None:
            raise ReportBatchError(
                "Complete onboarding before uploading reports",
                422,
                batch_id,
            )
        try:
            age = float(age)
        except (TypeError, ValueError) as error:
            raise ReportBatchError(
                "A valid onboarding age is required",
                422,
                batch_id,
            ) from error
        if not age.is_integer() or age < 13 or age > 120:
            raise ReportBatchError(
                "A valid onboarding age is required",
                422,
                batch_id,
            )
        age = int(age)

        validated = [
            _validated_extension(file, report_type)
            for file, report_type in zip(files, normalized_types)
        ]
        report_data = {field: None for field in REPORT_FIELDS}

        for index, (file, report_type, extension) in enumerate(
            zip(files, normalized_types, validated)
        ):
            filepath = os.path.join(
                UPLOAD_FOLDER,
                f"{uuid.uuid4().hex}{extension}",
            )
            temporary_paths.append(filepath)
            file.save(filepath)

            try:
                extracted = _normalize_extracted_data(
                    report_type,
                    _extract_file(filepath, report_type),
                )
            except Exception:
                file_results.append({
                    "file_index": index,
                    "report_type": report_type,
                    "status": "failed",
                    "extracted_data": {},
                    "error": "File processing failed",
                })
                raise
            if not _has_extracted_value(extracted):
                file_results.append({
                    "file_index": index,
                    "report_type": report_type,
                    "status": "failed",
                    "extracted_data": {},
                    "error": "No supported values could be extracted",
                })
                raise ReportBatchError(
                    f"No supported values could be extracted from {report_type}",
                    422,
                    batch_id,
                )

            report_data.update(extracted)
            file_results.append({
                "file_index": index,
                "report_type": report_type,
                "status": "processed",
                "extracted_data": extracted,
                "error": None,
            })

        calculations = calculate_batch_metrics(age, report_data)
        report_data["fib4"] = calculations["fib4"]["value"]
        report_data["apri"] = calculations["apri"]["value"]
        response = _build_response(
            batch_id,
            file_results,
            report_data,
            calculations,
        )
        completed = complete_report_batch(
            batch_id,
            user_id,
            age,
            report_data,
            file_results,
            response,
        )
        return completed, 201

    except ReportBatchError as error:
        mark_report_batch_failed(
            batch_id,
            user_id,
            str(error),
            file_results,
        )
        error.batch_id = batch_id
        raise
    except Exception as error:
        mark_report_batch_failed(
            batch_id,
            user_id,
            "Could not process report batch",
            file_results,
        )
        raise ReportBatchError(
            "Could not process report batch",
            500,
            batch_id,
        ) from error
    finally:
        for filepath in temporary_paths:
            try:
                os.remove(filepath)
            except OSError:
                pass
