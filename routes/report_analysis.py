from flask import Blueprint, request, jsonify

from services.report_analysis_service import (
    ReportNotFoundError,
    build_report_analysis,
)
from services.auth_service import auth_required, current_user_id

report_analysis_bp = Blueprint(
    "report_analysis",
    __name__
)

@report_analysis_bp.route(
    "/report-analysis",
    methods=["POST"]
)
@auth_required
def report_analysis():

    data = request.get_json(silent=True) or {}

    report_id = data.get("report_id")

    try:
        report_id = int(report_id) if report_id is not None else None
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "report_id must be an integer"
        }), 400
    if report_id is not None and report_id <= 0:
        return jsonify({
            "success": False,
            "error": "report_id must be a positive integer"
        }), 400

    try:
        result = build_report_analysis(current_user_id(), report_id)
    except ReportNotFoundError:
        return jsonify({
            "success": False,
            "error": "No saved report found for this user"
        }), 404
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not analyze report"
        }), 500

    if result is None:
        return jsonify({
            "success": False,
            "error": "User not found"
        }), 404

    return jsonify({
        "success": True,
        "report_analysis": result
    }), 200
