from flask import Blueprint, jsonify

from services.achievement_service import build_achievements
from services.auth_service import auth_required, current_user_id


achievements_bp = Blueprint("achievements", __name__)


@achievements_bp.route("/achievements", methods=["GET"])
@auth_required
def achievements():
    try:
        result = build_achievements(current_user_id())
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not load achievements",
        }), 500

    if result is None:
        return jsonify({
            "success": False,
            "error": "User not found",
        }), 404

    return jsonify({
        "success": True,
        **result,
    }), 200
