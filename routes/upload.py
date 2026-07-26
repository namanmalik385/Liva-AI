from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os

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

upload_bp = Blueprint("upload", __name__)

UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@upload_bp.route("/upload", methods=["POST"])
def upload_file():

    try:

        # Get file
        file = request.files.get("file")

        if not file:
            return jsonify({
                "success": False,
                "error": "No file uploaded"
            }), 400

        # Get report type
        report_type = request.form.get("report_type")

        if not report_type:
            return jsonify({
                "success": False,
                "error": "report_type is required"
            }), 400

        user_id = int(request.form.get("user_id"))

        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id is required"
            }), 400

        patient_data = get_patient_data(user_id)

        # Save PDF
        filename = secure_filename(file.filename)

        filepath = os.path.join(
            UPLOAD_FOLDER,
            filename
        )

        file.save(filepath)

        if report_type.lower() == "ultrasound":

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
        
        # Extract text
        text = extract_text(filepath)

        # Parse report
        results = {}

        if report_type.lower() == "lft":
            results = parse_lft(text)

        elif report_type.lower() == "cbc":
            results = parse_cbc(text)

        elif report_type.lower() == "coagulation":
            results = parse_coagulation(text)

        elif report_type.lower() == "afp":
            results = parse_afp(text)

        elif report_type.lower() == "hepatitis":
           results = parse_hepatitis(text)
        
        else:
            return jsonify({
                "success": False,
                "error": f"Unsupported report type: {report_type}"
            }), 400

        # Update patient data
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

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    
@upload_bp.route("/recent-reports/<int:user_id>", methods=["GET"])
def recent_reports(user_id):

    reports = get_recent_reports(user_id)

    return jsonify({
        "success": True,
        "recent_reports": reports
    })
