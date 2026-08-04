from flask import Blueprint, current_app, jsonify, request

from services.achievement_service import record_insights_explorer
from services.health_insights_service import build_health_insights
from services.report_analysis_service import ReportNotFoundError
from services.auth_service import auth_required, current_user_id


health_insights_bp = Blueprint("health_insights", __name__)


@health_insights_bp.route("/health-insights", methods=["POST"])
@auth_required
def health_insights():
    data = request.get_json(silent=True) or {}
    report_id = data.get("report_id")
    user_id = current_user_id()

    try:
        report_id = int(report_id) if report_id is not None else None
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "report_id must be an integer",
        }), 400
    if report_id is not None and report_id <= 0:
        return jsonify({
            "success": False,
            "error": "report_id must be a positive integer",
        }), 400

    try:
        insights = build_health_insights(
            user_id,
            report_id,
        )
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

    try:
        record_insights_explorer(user_id)
    except Exception:
        current_app.logger.exception(
            "Could not unlock Insights Explorer achievement"
        )

    return jsonify({
        "success": True,
        "health_insights": insights,
    }), 200
