from flask import Blueprint, jsonify, request

from services.auth_service import auth_required, current_user_id
from services.profile_service import (
    ProfileValidationError,
    build_profile,
    update_personal_info,
)


profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile", methods=["GET"])
@auth_required
def profile():
    try:
        profile_data = build_profile(current_user_id())
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not load profile",
        }), 500

    if profile_data is None:
        return jsonify({
            "success": False,
            "error": "User not found",
        }), 404

    return jsonify({
        "success": True,
        "profile": profile_data,
    }), 200


@profile_bp.route("/profile", methods=["PATCH"])
@auth_required
def update_profile():
    data = request.get_json(silent=True)

    try:
        profile_data = update_personal_info(current_user_id(), data)
    except ProfileValidationError as error:
        return jsonify({
            "success": False,
            "error": str(error),
        }), 400
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not update profile",
        }), 500

    if profile_data is None:
        return jsonify({
            "success": False,
            "error": "User not found",
        }), 404

    return jsonify({
        "success": True,
        "message": "Profile updated",
        "profile": profile_data,
    }), 200
