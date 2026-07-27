from flask import Blueprint, jsonify

from llm import get_liver_analysis
from services.auth_service import auth_required, current_user_id

insights_bp = Blueprint("insights", __name__)


@insights_bp.route("/insights", methods=["POST"])
@auth_required
def insights():

    try:
        result = get_liver_analysis(current_user_id())

        return jsonify({
            "success": True,
            "analysis": result
        })

    except Exception:

        return jsonify({
            "success": False,
            "error": "Could not load insights"
        }), 500
