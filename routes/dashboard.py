from flask import Blueprint, jsonify

from services.dashboard_service import build_dashboard
from services.auth_service import auth_required, current_user_id


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET"])
@auth_required
def dashboard():
    try:
        dashboard_data = build_dashboard(current_user_id())
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
