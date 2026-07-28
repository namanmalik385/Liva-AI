from flask import Blueprint, jsonify, request

from services.auth_service import auth_required, current_user_id
from services.timeline_service import TIMELINE_PERIODS, build_timeline


timeline_bp = Blueprint("timeline", __name__)


@timeline_bp.route("/timeline", methods=["GET"])
@auth_required
def timeline():
    period = request.args.get("period", "weekly").strip().lower()
    if period not in TIMELINE_PERIODS:
        return jsonify({
            "success": False,
            "error": "period must be weekly, monthly, or yearly",
        }), 400

    try:
        timeline_data = build_timeline(current_user_id(), period)
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not load health timeline",
        }), 500

    if timeline_data is None:
        return jsonify({
            "success": False,
            "error": "User not found",
        }), 404

    return jsonify({
        "success": True,
        "timeline": timeline_data,
    }), 200
