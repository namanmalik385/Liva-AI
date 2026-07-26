from flask import Blueprint, request, jsonify

from services.report_analysis_service import (
    ReportNotFoundError,
    build_report_analysis,
)

report_analysis_bp = Blueprint(
    "report_analysis",
    __name__
)

@report_analysis_bp.route(
    "/report-analysis",
    methods=["POST"]
)
def report_analysis():

    data = request.get_json(silent=True) or {}

    user_id = data.get("user_id")
    report_id = data.get("report_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "user_id is required"
        }), 400

    try:
        user_id = int(user_id)
        report_id = int(report_id) if report_id is not None else None
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "user_id and report_id must be integers"
        }), 400

    try:
        result = build_report_analysis(user_id, report_id)
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
