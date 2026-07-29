from flask import Blueprint, jsonify, request

from services.auth_service import auth_required, current_user_id
from services.support_service import (
    SupportValidationError,
    submit_support_request,
)


support_bp = Blueprint("support", __name__)


@support_bp.route("/help-support", methods=["POST"])
@auth_required
def submit_help_support():
    data = request.get_json(silent=True)

    try:
        ticket = submit_support_request(current_user_id(), data)
    except SupportValidationError as error:
        return jsonify({
            "success": False,
            "error": str(error),
        }), 400
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not submit support request",
        }), 500

    return jsonify({
        "success": True,
        "message": "Support request submitted",
        "ticket": ticket,
    }), 201
