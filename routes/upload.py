from flask import Blueprint, request, jsonify
import os
import uuid

from services.text_extractor import extract_text

from parsers.lft_parser import parse_lft
from parsers.cbc_parser import parse_cbc
from parsers.coagulation_parser import parse_coagulation
from parsers.afp_parser import parse_afp
from parsers.hepatitis_parser import parse_hepatitis
from services.ultrasound_model import predict_liver_condition

from models.patient_data import get_patient_data

from db import add_uploaded_report
from db import get_recent_reports
from services.auth_service import auth_required, current_user_id

upload_bp = Blueprint("upload", __name__)

UPLOAD_FOLDER = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "uploads")
)
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

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def _validated_extension(file, report_type):
    original_name = file.filename or ""
    extension = os.path.splitext(original_name)[1].lower()
    allowed_extensions = (
        ULTRASOUND_EXTENSIONS
        if report_type == "ultrasound"
        else LAB_EXTENSIONS
    )
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValueError(f"Allowed file types: {allowed}")

    header = file.stream.read(8)
    file.stream.seek(0)
    is_pdf = header.startswith(b"%PDF-")
    is_image = (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
    )
    if report_type == "ultrasound" and not is_image:
        raise ValueError("The uploaded ultrasound must be a JPEG or PNG image")
    if report_type != "ultrasound" and not is_pdf:
        raise ValueError("The uploaded lab report must be a valid PDF")

    return extension


@upload_bp.route("/upload", methods=["POST"])
@auth_required
def upload_file():
    filepath = None

    try:
        file = request.files.get("file")

        if file is None or not file.filename:
            return jsonify({
                "success": False,
                "error": "No file uploaded"
            }), 400

        report_type = request.form.get("report_type")

        if not isinstance(report_type, str) or not report_type.strip():
            return jsonify({
                "success": False,
                "error": "report_type is required"
            }), 400
        report_type = report_type.strip().lower()

        if report_type not in SUPPORTED_REPORT_TYPES:
            return jsonify({
                "success": False,
                "error": "Unsupported report type"
            }), 400

        try:
            extension = _validated_extension(file, report_type)
        except ValueError as error:
            return jsonify({
                "success": False,
                "error": str(error),
            }), 400

        user_id = current_user_id()

        patient_data = get_patient_data(user_id)

        filename = f"{uuid.uuid4().hex}{extension}"

        filepath = os.path.join(
            UPLOAD_FOLDER,
            filename
        )

        file.save(filepath)

        if report_type == "ultrasound":

            result = predict_liver_condition(filepath)

            patient_data["ultrasound_prediction"] = result

            add_uploaded_report(
                user_id=user_id,
                report_type=report_type
            )

            return jsonify({
                "success": True,
                "report_type": report_type,
                "prediction": result
            })
        
        text = extract_text(filepath)

        results = {}

        if report_type == "lft":
            results = parse_lft(text)

        elif report_type == "cbc":
            results = parse_cbc(text)

        elif report_type == "coagulation":
            results = parse_coagulation(text)

        elif report_type == "afp":
            results = parse_afp(text)

        elif report_type == "hepatitis":
            results = parse_hepatitis(text)

        patient_data.update(results)

        add_uploaded_report(
            user_id=user_id,
            report_type=report_type
        )

        return jsonify({
            "success": True,
            "report_type": report_type,
            "extracted_data": results,
            "patient_data": patient_data
        })

    except Exception:

        return jsonify({
            "success": False,
            "error": "Could not process uploaded report"
        }), 500
    finally:
        if filepath is not None:
            try:
                os.remove(filepath)
            except OSError:
                pass


@upload_bp.route("/recent-reports", methods=["GET"])
@upload_bp.route(
    "/recent-reports/<int:requested_user_id>",
    methods=["GET"],
)
@auth_required
def recent_reports(requested_user_id=None):
    user_id = current_user_id()

    if requested_user_id is not None and requested_user_id != user_id:
        return jsonify({
            "success": False,
            "error": "Access denied",
        }), 403

    reports = get_recent_reports(user_id)

    return jsonify({
        "success": True,
        "recent_reports": reports
    })
