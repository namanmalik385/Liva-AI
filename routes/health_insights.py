from flask import Blueprint, jsonify, request

from services.health_insights_service import build_health_insights
from services.report_analysis_service import ReportNotFoundError


health_insights_bp = Blueprint("health_insights", __name__)


@health_insights_bp.route("/health-insights", methods=["POST"])
def health_insights():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    report_id = data.get("report_id")

    if not user_id:
        return jsonify({
            "success": False,
            "error": "user_id is required",
        }), 400

    try:
        user_id = int(user_id)
        report_id = int(report_id) if report_id is not None else None
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "user_id and report_id must be integers",
        }), 400

    try:
        insights = build_health_insights(user_id, report_id)
    except ReportNotFoundError:
        return jsonify({
            "success": False,
            "error": "No saved report found for this user",
        }), 404
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not load health insights",
        }), 500

    if insights is None:
        return jsonify({
            "success": False,
            "error": "User not found",
        }), 404

    return jsonify({
        "success": True,
        "health_insights": insights,
    }), 200
