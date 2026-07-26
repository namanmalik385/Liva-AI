from flask import Blueprint, jsonify, request

from services.dashboard_service import build_dashboard


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET"])
def dashboard():
    user_id = request.args.get("user_id", type=int)

    if not user_id:
        return jsonify({
            "success": False,
            "error": "user_id is required",
        }), 400

    try:
        dashboard_data = build_dashboard(user_id)
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not load dashboard",
        }), 500

    if dashboard_data is None:
        return jsonify({
            "success": False,
            "error": "User not found",
        }), 404

    return jsonify({
        "success": True,
        "dashboard": dashboard_data,
    }), 200
