from flask import Blueprint, request, jsonify

from models.patient_data import clear_patient_data, get_patient_data

from calculators.fib4 import calculate_fib4
from calculators.apri import calculate_apri

from db import add_report

calculate_bp = Blueprint("calculate", __name__)


@calculate_bp.route("/calculate", methods=["POST"])
def calculate():

    try:

        data = request.get_json()

        user_id = int(data["user_id"])
        patient_data = get_patient_data(user_id)

        age = float(data["age"])
        ast_uln = None

        if patient_data.get("ast_uln") is not None:
            ast_uln = float(patient_data["ast_uln"])

        can_calculate = (
            patient_data.get("ast") is not None
            and patient_data.get("alt") is not None
            and patient_data.get("platelets") is not None
            and ast_uln is not None
        )

        fib4_score = None
        apri_score = None

        if can_calculate:

            fib4_score = calculate_fib4(
                age=age,
                ast=patient_data["ast"],
                alt=patient_data["alt"],
                platelets=patient_data["platelets"]
            )

            apri_score = calculate_apri(
                ast=patient_data["ast"],
                ast_uln=ast_uln,
                platelets=patient_data["platelets"]
            )

            fib4_score = round(fib4_score, 2)
            apri_score = round(apri_score, 2)

            patient_data["fib4"] = fib4_score
            patient_data["apri"] = apri_score

        report_id = add_report(
            user_id=user_id,
            age=age,
            platelets=patient_data.get("platelets"),
            ast=patient_data.get("ast"),
            alt=patient_data.get("alt"),
            bilirubin=patient_data.get("total_bilirubin"),
            albumin=patient_data.get("albumin"),
            inr=patient_data.get("inr"),
            pt=patient_data.get("pt"),
            afp=patient_data.get("afp"),
            hbsag=patient_data.get("hbsag"),
            anti_hcv=patient_data.get("anti_hcv"),
            ast_uln=ast_uln,
            apri=apri_score,
            fib4=fib4_score,
            ultrasound_prediction=patient_data.get("ultrasound_prediction")
        )

        if report_id is None:
            return jsonify({
                "success": False,
                "error": "Failed to save report"
            }), 500

        report_data = {
            "user_id": user_id,
            "age": age,
            "ast_uln": ast_uln,
            "platelets": patient_data.get("platelets"),
            "ast": patient_data.get("ast"),
            "alt": patient_data.get("alt"),
            "total_bilirubin": patient_data.get("total_bilirubin"),
            "albumin": patient_data.get("albumin"),
            "inr": patient_data.get("inr"),
            "pt": patient_data.get("pt"),
            "afp": patient_data.get("afp"),
            "hbsag": patient_data.get("hbsag"),
            "anti_hcv": patient_data.get("anti_hcv"),
            "fib4": fib4_score,
            "apri": apri_score,
            "ultrasound_prediction": patient_data.get("ultrasound_prediction"),
        }
        clear_patient_data(user_id)

        return jsonify({
            "success": True,
            "report_id": report_id,
            "fib4": fib4_score,
            "apri": apri_score,
            "report_data": report_data
        })
    
    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
